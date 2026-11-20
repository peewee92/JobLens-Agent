"""Deterministic extraction of explicit fields; never infer a missing employer."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag

from app.application.job_requirements.description_readiness import MIN_DESCRIPTION_CHARS

from .models import InterventionReason, QualityGrade

JD_SIGNALS = re.compile(
    r"\b(?:responsibilit(?:y|ies)|requirements?|qualifications?|what you(?:'ll| will) do|"
    r"about the role|what you bring|what we(?:'re| are) looking for)\b|职责|任职要求|岗位要求|职位要求|工作内容|资格要求",
    re.I,
)
_LOGIN_PATH = re.compile(r"(?:^|/)(?:login|log-in|signin|sign-in|sso|auth/login)(?:/|$)", re.I)
_CHALLENGE_PATH = re.compile(r"(?:^|/)(?:captcha|challenge|security-verification)(?:/|$)|/cdn-cgi/challenge", re.I)
_LOGIN_TEXT = re.compile(r"^(?:log ?in|sign ?in|please log in|login required|请登录|登录后查看|请先登录)(?:\b|[\s：:！!]|$)|请(?:先)?登录|登录后(?:才可)?查看", re.I)
_CAPTCHA_TEXT = re.compile(r"\bcaptcha\b|验证码|人机验证|verify (?:that )?you(?: are|'re) human", re.I)
_CHALLENGE_TEXT = re.compile(r"security check|just a moment|access denied|verify your browser|checking your browser|too many requests|安全验证|访问受限|请求过于频繁", re.I)
_NOISE = (
    "script, style, template, noscript, nav, footer, aside, form, button, [hidden], [aria-hidden=true], "
    "[role=navigation], [role=complementary], .related-jobs, #related-jobs, .recommended-jobs"
)
_DESCRIPTION = (
    "[itemprop=description], [data-job-description], #job-description, .job-description, "
    ".posting-description, .job-post-description, .section-wrapper, #content[data-job]"
)
_MAIN = "main, [role=main], article, .posting-page, #content"
_BLOCK_BOUNDARIES = ("p", "li", "br", "div", "section", "h1", "h2", "h3", "h4", "h5", "tr", "dd", "dt")
_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_GREENHOUSE_POSTING = re.compile(r"/[^/]+/jobs/[0-9]+(?:-[0-9]+)?/?")


@dataclass(frozen=True)
class ExtractedJob:
    title: str
    company: str
    description: str

    @property
    def usable(self) -> bool:
        return bool(self.title and self.company and self.description)


def normalize_text(text: str) -> str:
    return "\n".join(line for raw in text.splitlines() if (line := " ".join(raw.split())))


def label(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def description_text(tag: BeautifulSoup | Tag) -> str:
    for node in tag.select(",".join(_BLOCK_BOUNDARIES)):
        node.insert_before("\n")
        if node.name != "br":
            node.insert_after("\n")
    return normalize_text(tag.get_text())


def only_posting(value: object) -> list[dict]:
    pending = [value]
    postings = []
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            kinds = node.get("@type")
            if not isinstance(kinds, list):
                kinds = [kinds]
            if any(kind in ("JobPosting", "https://schema.org/JobPosting", "http://schema.org/JobPosting") for kind in kinds):
                postings.append(node)
            pending.append(node.get("@graph"))
    return postings


def grade_description(text: str) -> QualityGrade:
    if not text:
        return "unavailable"
    if len(text) < MIN_DESCRIPTION_CHARS:
        return "card_only"
    return "full_jd" if len(text) >= 180 and JD_SIGNALS.search(text) else "partial_jd"


def url_intervention(url: str) -> InterventionReason | None:
    path = unquote(urlsplit(url).path)
    if _LOGIN_PATH.search(path):
        return "login_required"
    if _CHALLENGE_PATH.search(path):
        return "captcha_detected" if "captcha" in path.casefold() else "anti_bot_challenge"
    return None


class HtmlPosting:
    def __init__(self, html: bytes | str, *, content_type: str = "") -> None:
        encoding = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type, re.I)
        self.soup = BeautifulSoup(html, "html.parser", from_encoding=encoding[1] if encoding and isinstance(html, bytes) else None)
        self.has_scripts = bool(self.soup.find("script", src=True) or self.soup.select_one("#root, #app, #__next, #__nuxt"))

    def _field(self, selectors: str) -> str:
        field = self.soup.select_one(selectors)
        if field is None:
            return ""
        return label(field.get("content") or field.get("data-company-name") or field.get_text(" ", strip=True))

    def intervention(self, url: str, status: int) -> InterventionReason | None:
        hint = url_intervention(url)
        if hint:
            return hint
        heading = " ".join(node.get_text(" ", strip=True) for node in self.soup.select("title, h1")[:5])
        region = self.soup.select_one("main, [role=main], body")
        primary = region.get_text(" ", strip=True)[:420] if region is not None else ""
        if _CAPTCHA_TEXT.search(heading) or (
            _CAPTCHA_TEXT.search(primary) and self.soup.select_one("iframe[src*=captcha], #challenge-form, [data-sitekey]")
            and not JD_SIGNALS.search(primary)
        ):
            return "captcha_detected"
        if _LOGIN_TEXT.search(heading) or (
            (_LOGIN_TEXT.search(primary) or self.soup.select_one("input[type=password]"))
            and not JD_SIGNALS.search(primary)
        ) or status == 401:
            return "login_required"
        if status in {403, 429} or _CHALLENGE_TEXT.search(heading) or self.soup.select_one("#challenge-form, #cf-challenge-running"):
            return "anti_bot_challenge"
        return None

    def structured(self) -> ExtractedJob | None:
        postings = []
        for script in self.soup.find_all("script", type="application/ld+json"):
            try:
                value = json.loads(script.string or script.get_text())
            except (ValueError, RecursionError):
                continue
            postings.extend(only_posting(value))
        if len(postings) != 1:
            return None
        posting = postings[0]
        employer = posting.get("hiringOrganization")
        description = posting.get("description")
        if isinstance(description, str):
            body = BeautifulSoup(description, "html.parser")
            for tag in body.select(_NOISE):
                tag.decompose()
            description = description_text(body)
        return ExtractedJob(
            label(posting.get("title")),
            label(employer.get("name") if isinstance(employer, dict) else employer),
            description if isinstance(description, str) else "",
        )

    def semantic(self, structured: ExtractedJob | None = None, *, source_url: str) -> tuple[ExtractedJob, int]:
        source = urlsplit(source_url)
        greenhouse = source.hostname in _GREENHOUSE_HOSTS and _GREENHOUSE_POSTING.fullmatch(source.path)
        greenhouse_heading = self._field(".job__header h1") if greenhouse else ""
        title = greenhouse_heading or self._field("main h1, article h1, h1, meta[itemprop=title]")
        company = self._field(
            "[itemprop=hiringOrganization] [itemprop=name], meta[itemprop=hiringOrganization], "
            "meta[name=company], meta[property='job:company'], [data-company-name], .company-name, .posting-headline .company"
        ) or (structured.company if structured else "")
        if not company and greenhouse_heading:
            page_title = self._field("head title, title")
            prefix = f"Job Application for {greenhouse_heading} at "
            if page_title.startswith(prefix):
                company = page_title.removeprefix(prefix).strip()
        for node in self.soup.select(_NOISE):
            node.decompose()
        raw = len(normalize_text(self.soup.get_text(" ")))
        region = self.soup.select_one(".job__description") if greenhouse else None
        if region is None:
            region = self.soup.select_one(_DESCRIPTION)
        explicit = region is not None
        if region is None:
            region = self.soup.select_one(_MAIN)
        lines = description_text(region).splitlines() if region is not None else []
        title = title or (structured.title if structured else "")
        text = "\n".join(line for line in lines if line not in {title, company})
        # An arbitrary main region is not itself evidence of a job description.
        if not explicit and not JD_SIGNALS.search(text):
            text = ""
        return ExtractedJob(title, company, text), raw


_A11Y_LINE = re.compile(r'^\s*-\s+(heading|paragraph|listitem|text|generic|article|main)\b(.*)$')
_A11Y_METADATA = re.compile(r"\s+\[[\w-]+(?:=[^\]]+)?\]")


def a11y_description(snapshot: str, title: str, company: str) -> tuple[str, int]:
    lines: list[str] = []
    blocked_indent: int | None = None
    node_count = 0
    for line in snapshot.splitlines():
        if not line.lstrip().startswith("- "):
            continue
        node_count += 1
        indent = len(line) - len(line.lstrip())
        if blocked_indent is not None and indent > blocked_indent:
            continue
        blocked_indent = None
        if re.match(r"^\s*- (?:navigation|banner|contentinfo|complementary|form|link|button)\b", line):
            blocked_indent = indent
            continue
        match = _A11Y_LINE.match(line)
        if match:
            value = _A11Y_METADATA.sub("", match[2]).strip().strip(":").strip().strip('"')
            if value and value not in {title, company} and (not lines or lines[-1] != value):
                lines.append(value)
    text = normalize_text("\n".join(lines))
    return (text if JD_SIGNALS.search(text) else ""), node_count
