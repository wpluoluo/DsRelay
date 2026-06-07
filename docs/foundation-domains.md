# 基础域梳理

当前系统后续增强必须围绕五个基础域展开，避免继续在页面和单个 service 中散落字段。

## 1. 用户体系

核心字段：

- `id`
- `name`
- `external_key`
- `source_type`
- `role`
- `status`
- `balance_cents`
- `concurrency_limit`
- `allowed_group_ids`
- `enabled`

目标：

- 用户身份、额度、并发、允许分组统一归口
- 后续 API Key、订阅、支付订单均归属于用户

## 2. 权限体系

当前先落最小模型：

- `role`
- `status`
- `allowed_group_ids`

当前规则：

- 后台接口统一按 `admin` 角色访问
- 普通业务能力通过 `status` 和 `allowed_group_ids` 控制
- 不单独建设细粒度权限点和授权矩阵，保持与 SUB2 一致的简单模型

## 3. 分组体系

核心字段：

- `id`
- `name`
- `description`
- `platform`
- `is_exclusive`
- `rate_multiplier`
- `enabled`
- `sort_order`

目标：

- 分组既承担业务归类，也承担协议/渠道/倍率约束
- 后续协议绑定、订阅绑定、可见性控制都挂到分组

## 4. 协议体系

核心概念：

- `openai`
- `responses`
- `anthropic`
- `gemini`

目标：

- 协议支持能力成为显式模型，不再只散落在运行时判断中
- 线路、模型、参数支持矩阵以协议为中心组织

## 5. 支付体系

核心字段：

- `payment_channel`
- `payment_order`
- `payment_status`
- `provider_payload`
- `webhook_event`

目标：

- 订单状态流转明确
- 渠道配置与订单履约分离
- 回调幂等与订阅发放逻辑稳定

## 当前执行原则

- 先做统一模型与校验
- 再做接口与动作
- 最后再补更复杂的前端交互
