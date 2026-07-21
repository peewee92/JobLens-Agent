# ADR-0001：MVP 使用单 Career Agent，并将 Collector 独立为数据入口

## 状态

Accepted

## 决策

1. 浏览器插件保持 Job Collector 定位；
2. 求职分析放入独立 JobLens-Agent 项目；
3. MVP 只使用一个 Career Agent + Tools；
4. MVP 数据接入先使用 JSON Import；
5. 自动投递、多 Agent、招聘者自动沟通不进入 MVP。

## 原因

当前最大未验证价值不是“Agent 能否自动操作更多网站”，而是：

> 基于真实岗位和真实个人经历，能否产生可信、可解释、可执行的职业决策。

先验证这条价值链，可以最大限度复用现有 Collector，并控制系统复杂度。
