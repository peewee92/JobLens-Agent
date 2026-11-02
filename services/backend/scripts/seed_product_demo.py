"""Three synthetic product examples through existing HTTP handlers, not seeded reports or release gates."""
import json
import os
from pathlib import Path


def main():
    from app.core.config import get_settings
    settings = get_settings()
    directory = Path(os.environ['JOBLENS_DEMO_DIRECTORY']).resolve()
    marker = json.loads((directory / 'joblens-demo.json').read_text())
    if (settings.app_env != 'demo' or settings.database_url != f'sqlite:///{directory / "demo.db"}'
        or marker != {'kind':'joblens-synthetic-demo','version':1,'status':'initializing','empty':False}
        or settings.requirement_extractor_provider != 'fixture'
        or any(p != 'disabled' for p in (settings.semantic_match_provider,settings.profile_extractor_provider,
            settings.career_intent_provider,settings.requirement_extractor_fallback_provider)) or settings.openai_api_key):
        raise RuntimeError('只允许在专属零模型合成演示目录首次初始化。')
    from fastapi.testclient import TestClient
    from app.main import app
    def request(client, method, path, body=None):
        response = client.request(method,'/api/v1'+path,json=body)
        if response.status_code not in (200,201):
            raise RuntimeError(f'合成示例初始化失败：{method} {path} HTTP {response.status_code}')
        return response.json()
    with TestClient(app) as client:
        if client.get('/api/v1/profile').status_code != 404 or request(client,'GET','/jobs')['total']:
            raise RuntimeError('演示库不是空库，拒绝覆盖。')
        request(client,'PUT','/profile',dict(expectedVersion=0,headline='合成演示资料，不是真实求职经历',yearsOfExperience=2,
            evidence=[dict(key='python-demo',type='project',summary='使用 Python 开发并维护合成服务，保留检查记录。',source='合成演示样本，不是真实职业经历')],
            skills=[dict(name='Python',level='working',evidenceKeys=['python-demo'])]))
        request(client,'PUT','/search-intent',dict(expectedVersion=0,targetRoles=['后端工程师'],cities=[],remoteAccepted=None,
            minimumSalaryK=None,seniority=None,employmentTypes=[],excludeKeywords=[],hardConstraints=[],softPreferences=[]))
        jobs = [
            ('Python 后端工程师','任职要求：熟练掌握 Python，能够说明真实的服务开发与维护经验。\n加分项：熟悉 Docker，并能够说明容器部署经验。'),
            ('TypeScript 工程师','任职要求：熟练掌握 TypeScript，并能够说明真实的类型系统设计与工程维护经验。'),
            ('高级后端工程师','任职要求：至少5年以上工作经验，能够以真实工作年限记录说明满足这一工作经验要求。')]
        for index,(title,description) in enumerate(jobs):
            job = request(client,'POST','/job-imports/manual',dict(title=title,company='合成演示公司（非真实招聘）',description=description))['jobId']
            facts = request(client,'POST',f'/jobs/{job}/requirement-extractions')
            # Explicitly synthetic preparation for this demo only, never a formal model release approval.
            request(client,'POST',f'/jobs/{job}/requirement-confirmations',dict(actionId=f'demo-check-{index}',
                extractionId=facts['extractionId'],inputHash=facts['inputHash'],factsDigest=facts['factsDigest'],confirmed=True))
            request(client,'POST',f'/jobs/{job}/match-report')
    print('已通过现有接口准备合成资料、意向和三份离线报告；尚未创建分析运行、工作区或正式模型放行记录。')


if __name__ == '__main__':
    main()
