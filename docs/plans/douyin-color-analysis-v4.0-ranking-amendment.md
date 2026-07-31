# 抖音自有服装颜色表现分析系统 Ranking Amendment v4.0（修订版）

> 本文件是 v3.1 规格的排名对象补丁，与 v3.1 冲突时以本文件为准。v3.1 其余约束（采集协议、安全、审计、迁移、四阶段开关等）继续有效。

## 1. 变更背景

v3.1 原约束"禁止扩展为整套穿搭、多件归因"与实际业务需求冲突。业务核心目标是分析**整套穿搭**的表现，单件分榜为次要派生。AI 不做衣物识别，全部由运营人工输入文字标注。

**关键澄清（2026-07-31）：**
- 整套穿搭**组合**为主要排名对象（不是颜色组合）
- 颜色是次要信息，人工可选输入，仅作 SKU 区分参考，不参与计算
- 排名精度到 **SKU 层**（款号+颜色通过 SKU 编码区分）
- 一段曲线归一套穿搭（不再是单件衣物）

## 2. 核心单位：整套穿搭

### 2.1 基本单位
- **一段曲线归一套穿搭**（不再是单件衣物）
- 视频中以整套穿搭为单位进行标注
- 一套穿搭 = 人工填写的 N 件衣物组合（2~N 件，冬天可能 4 件甚至更多，夏天可能 2 件）
- 每件衣物包含：衣物位（outer/top/bottom/...）+ 款号（style_id）+ 可选 SKU 编码（sku_code）
- **颜色不直接存储**，通过 SKU 编码区分（SKU 表中包含颜色信息）

### 2.2 排名对象（3 个，主次分明）

| 排名 | 优先级 | 对象 | 聚合维度 | 曲线来源 |
| --- | --- | --- | --- | --- |
| 整套穿搭 | **主要** | 整套穿搭的款式组合 | 款式组合（不含颜色） | 整套曲线 |
| 上衣（含外套） | 次要 | 单件上衣类衣物 | 款号+SKU | 复用整套曲线 |
| 裤子（含裙） | 次要 | 单件下装 | 款号+SKU | 复用整套曲线 |

**排名口径：**
- **整套穿搭排名**：同账号 + 同款式组合键 + 同观察窗口 + 同位置段
  - 组合键 = 参与衣物的 (position:style_id) 按 position 升序拼接，**不含 color_id**
  - 同款式组合的不同颜色（SKU）合并为一个样本
- **单件分榜**：从整套穿搭中按衣物位拆出，**复用整套曲线**，不拆分曲线时段
  - 上衣分榜 = garment_position ∈ {outer, top} 的单件
  - 裤子分榜 = garment_position = bottom 的单件（含裙）
  - 单件样本按款号+SKU 独立展示（颜色通过 SKU 区分，不参与计算）
- 其他衣物位（none/other）不参与任何排名

### 2.3 样本门槛
- 整套穿搭平均排名：至少 3 条不同视频
- 整套穿搭稳定性排名：至少 5 条不同视频，标准差 n-1
- 单件分榜：同 v3.1 门槛

### 2.4 颜色处理原则
- 颜色是**次要参考信息**，不参与排名计算
- 颜色通过 SKU 编码区分（garment_skus 表含 color_id 字段）
- garment_colors 表保留，但排名计算时忽略 color_id
- 导出报告时可展示 SKU 对应的颜色名称作为参考

## 3. 数据模型变更

### 3.1 video_clips 语义变更（核心）
- **旧（v3.1）**：一段曲线归一件主要衣物（style_id + color_id）
- **新（v4.0）**：一段曲线归一套穿搭

```sql
-- video_clips 新增字段（替代原 style_id + color_id 单件语义）
ALTER TABLE douyin.video_clips
ADD COLUMN outfit_parts_json JSONB NOT NULL DEFAULT '[]';
-- 格式：[{"position": "outer", "style_id": 100, "sku_code": "WZ001-RED-M"},
--        {"position": "top", "style_id": 300, "sku_code": "WZ002-BLUE-L"},
--        {"position": "bottom", "style_id": 500, "sku_code": null}]
-- position 必填；style_id 必填；sku_code 可选（null 表示未指定 SKU）
-- 颜色不直接存储，通过 sku_code 关联 garment_skus.color_id 派生
-- 至少 2 件才算一套穿搭；不写死件数，适配 2~N 件

-- 保留 style_id + color_id 字段为可空，仅供向后兼容
-- v4.0 中不再作为主要标注字段
```

### 3.2 focus_status 语义变更
- **旧（v3.1）**：clear_primary=单件清晰；multi_focus=多件无法选主；unclear=无法判断
- **新（v4.0）**：
  - `clear_primary` = 整套穿搭清晰可见，可参与排名
  - `multi_focus` = 多套穿搭同屏，无法选出主套，只进质量排除
  - `unclear` = 无法判断整套穿搭，只进质量排除

CHECK 约束调整：
```sql
-- v4.0: clear_primary 要求 outfit_parts_json 至少 2 件
CHECK (
  (focus_status = 'clear_primary' AND jsonb_array_length(outfit_parts_json) >= 2)
  OR
  (focus_status IN ('multi_focus', 'unclear') AND jsonb_array_length(outfit_parts_json) = 0)
)
```

### 3.3 garment_styles 保留 garment_position
```sql
ALTER TABLE douyin.garment_styles
ADD COLUMN garment_position VARCHAR(16) NOT NULL DEFAULT 'none';
-- 枚举：outer / top / bottom / none
```

### 3.4 garment_colors 表保留（计算忽略）
- 保留 garment_colors 表和已有数据
- 排名计算时忽略 color_id
- 颜色信息通过 garment_skus.sku_code -> garment_skus.color_id -> garment_colors 关联展示

### 3.5 garment_skus 表（颜色信息的载体）
- garment_skus 表保留原有结构（sku_code, color_id, size_name 等）
- outfit_parts_json 中的 sku_code 关联此表
- 排名展示时通过 SKU 关联出颜色名称作为参考

### 3.6 outfit_combinations 表（主要指标载体）
```text
outfit_combinations(
  id, account_id, video_id,
  observation_window,
  combination_key,              -- 参与衣物的 (position:style_id) 按 position 升序拼接，不含 color_id
  participant_count,            -- 参与衣物数（>=2）
  annotation_set_hash,
  retention_snapshot_id,
  bounce_snapshot_id_nullable,
  created_at,
  UNIQUE(account_id, video_id, observation_window, combination_key)
)
```

### 3.7 outfit_color_metrics 表（主要排名指标，命名沿用但口径为款式组合）
字段口径参照 video_color_metrics，但唯一键改为：
```text
UNIQUE(
  account_id, combination_key, observation_window,
  metric_version, metric_input_hash
)
```
- combination_key 不含 color_id
- 同款式组合的不同颜色（SKU）合并为一个样本

### 3.8 video_color_metrics 保留为次要派生（单件分榜）
- 单件分榜指标仍存 video_color_metrics
- 新增 garment_position 字段用于分榜筛选
- **曲线复用整套曲线**，不拆分时段
- 一套穿搭可派生多条 video_color_metrics（每件衣物一条）
- 新增 sku_code 字段（可空），用于单件分榜的 SKU 层级展示
- 精度到 SKU 层：同款号不同 SKU（颜色）作为独立样本展示

```sql
ALTER TABLE douyin.video_color_metrics
ADD COLUMN garment_position VARCHAR(16) NOT NULL DEFAULT 'none',
ADD COLUMN sku_code VARCHAR(64);  -- 可空，用于 SKU 层级展示
```

## 4. 人工标注入口

### 4.1 前端输入
标注页以**整套穿搭**为单位：
- 一个标注片段 = 一套穿搭的出现时段（start_ms ~ end_ms）
- 片段内可动态添加 N 件衣物（每件：衣物位选择 + 款号 + 可选 SKU）
- 衣物位可扩展（当前 outer/top/bottom，未来可加 dress/outer 等）
- **款号必填，SKU 可选**（SKU 包含颜色信息）
- AI 不做识别，全部人工输入

### 4.2 入口适配
- 不写死 3 件，支持 2~N 件
- 衣物位枚举可扩展
- 至少 2 件才算一套穿搭（clear_primary）

### 4.3 颜色输入说明
- 颜色不单独输入，通过选择 SKU 间接指定
- 运营选择款号后，可从该款号的 SKU 列表中选择具体 SKU（含颜色+尺码）
- 也可不选 SKU，只标款号（表示该件衣物的颜色不区分）

## 5. 指标计算

### 5.1 主要：整套穿搭指标（outfit_color_metrics）
- 一段曲线归一套穿搭
- combination_key 标识穿搭款式组合（不含 color_id）
- 留存/跳出独立选快照、独立计算
- 跳出保持 platform_bounce_curve_value，三视频语义验证前不排名
- 同款式组合的不同颜色（SKU）合并为一个样本

### 5.2 次要：单件分榜指标（video_color_metrics）
- 从整套穿搭中按衣物位拆出
- **复用整套曲线**，不拆分时段
- 一套穿搭的上衣部分 -> video_color_metric (garment_position=top/outer, style_id, sku_code)
- 一套穿搭的裤子部分 -> video_color_metric (garment_position=bottom, style_id, sku_code)
- 其他衣物位不生成单件指标
- 精度到 SKU 层：同款号不同 SKU（颜色）作为独立样本展示

### 5.3 颜色不参与计算
- 所有 hash（annotation_set_hash, metric_input_hash, combination_key）均不含 color_id
- 颜色仅作为展示参考，通过 SKU 关联
- 报告中可展示"该样本包含的 SKU 及对应颜色"作为参考信息

## 6. 保留的 v3.1 约束

- multi_focus / unclear 只进入质量排除统计
- 留存与跳出独立选快照、独立计算、独立计数
- 跳出在三视频逐点语义验收前只能叫 platform_bounce_curve_value，不参与任何排名
- 报告只比较同账号、同观察窗口、同位置段
- 64 位作品 ID 全链路字符串
- 不输出 Cookie/JWT/token/签名 URL/验证码

## 7. 删除的 v3.1 约束

- 删除"禁止扩展为整套穿搭"
- 删除"一段曲线归一件主要衣物"（改为归一套穿搭）
- 删除"第一版不记录同屏所有衣物"（改为记录整套穿搭的多件）
- 删除"颜色参与排名计算"（颜色降级为 SKU 参考信息）
- 保留"不做自动识别、搭配关系、组合评分、联合归因"（整套只是组合键，不做搭配评分）

## 8. 报告展示

- 报告页提供 3 个独立 Tab：整套穿搭（主要）/ 上衣（次要）/ 裤子（次要）
- 整套穿搭 Tab 为默认视图
- 整套穿搭 Tab 在片段具备 ≥2 件衣物时才出现样本
- 整套穿搭排名按款式组合聚合，同组合不同颜色合并
- 上衣 Tab 聚合 outer+top，复用整套曲线，按款号+SKU 独立展示
- 裤子 Tab 只含 bottom，复用整套曲线，按款号+SKU 独立展示
- 报告可展示每个样本包含的 SKU 及对应颜色作为参考
- 其他衣物位的片段在视频列表可见，但不进入任何排名 Tab

## 9. 对已实现代码的影响

### 9.1 需要调整
- `video_clips` 模型：新增 outfit_parts_json（含 position+style_id+可选 sku_code），调整 CHECK 约束
- `compute_video_color_metric`：改为从 outfit_parts 派生单件指标，复用整套曲线，加 sku_code
- `compute_outfit_metric`：成为主要指标计算入口，combination_key 不含 color_id
- `build_combination_key`：移除 color_id，改为 position:style_id 拼接
- `focus_status` 语义：所有相关服务和测试更新
- `video_color_metrics` 模型：新增 sku_code 字段

### 9.2 保留
- `garment_styles.garment_position` 字段
- `garment_colors` 表（计算忽略，展示参考）
- `garment_skus` 表（颜色的载体）
- `outfit_combinations` / `outfit_color_metrics` 表结构（combination_key 口径调整）
- `douyin_color_curve_service.py` 的曲线归一化函数（与穿搭单位无关）

### 9.3 已实现但需修正
- `douyin_color_outfit_service.py` 的 `build_combination_key`：移除 color_id
- `derive_outfit_participants`：返回值移除 color_id，加 sku_code
- `compute_annotation_set_hash`：移除 color_id，加 sku_code
- `compute_metric_input_hash`：口径不变（不含 color_id）

## 10. 迁移与回滚

- 新增字段和表通过 Alembic 迁移，不动既有数据
- 存量 video_clips 的 style_id + color_id 保留，outfit_parts_json 默认空数组
- 存量 garment_colors 数据保留，计算时忽略
- 回滚：关闭整套排名开关，单件排名仍可用；不删除新表

## 11. 与 v3.1 的关键差异总结

| 维度 | v3.1 | v4.0 |
| --- | --- | --- |
| 标注单位 | 单件主要衣物 | 整套穿搭 |
| 曲线归属 | 一段曲线归一件衣物 | 一段曲线归一套穿搭 |
| 主要排名 | 同款不同色 | 整套穿搭款式组合 |
| 颜色作用 | 排名维度 | 次要参考（通过 SKU 区分） |
| 排名精度 | 颜色层 | SKU 层（颜色为参考） |
| 单件分榜 | 无 | 次要派生（上衣/裤子） |
| focus_status | 单件清晰度 | 整套清晰度 |
| 整套穿搭 | 禁止 | 主要目标 |
