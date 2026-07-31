# 抖音自有服装颜色表现分析系统 Ranking Amendment v4.0

> 本文件是 v3.1 规格的排名对象补丁，与 v3.1 冲突时以本文件为准。v3.1 其余约束（采集协议、安全、审计、迁移、四阶段开关等）继续有效。

## 1. 变更背景

v3.1 原约束"禁止扩展为整套穿搭、多件归因"与实际业务需求冲突。业务需要：
- 整套穿搭的颜色表现排名
- 上衣（含外套）单件排名
- 裤子（含裙）单件排名

AI 不做衣物识别，全部由运营人工输入文字标注。系统只负责输入框、存储、校验、排名聚合。

## 2. 排名对象（替换 v3.1 §4.3 排名口径）

系统产出 3 个独立的颜色表现排名，互不混用：

### 2.1 整套穿搭排名
- 对象：同一视频内 ≥2 件合格衣物（2件套/3件套均可，缺外套允许）的组合
- 组合键：参与衣物的 (款号+颜色) 规范化组合，按 garment_position 升序排序后拼接
- 比较维度：同账号 + 同组合键 + 同观察窗口 + 同位置段
- 样本门槛：平均排名至少 3 条不同视频；稳定性排名至少 5 条不同视频
- 单视频多件合格片段时，整套聚合为一个样本，曲线按片段时长加权

### 2.2 上衣分榜（含外套）
- 对象：garment_position ∈ {outer, top} 的单件衣物
- 比较维度：同账号 + 同款号 + 同颜色 + 同观察窗口 + 同位置段
- 样本门槛：同 v3.1

### 2.3 裤子分榜（含裙）
- 对象：garment_position = bottom 的单件衣物（含长裤、短裤、裙裤、半裙、长裙等所有下装）
- 比较维度：同账号 + 同款号 + 同颜色 + 同观察窗口 + 同位置段
- 样本门槛：同 v3.1

### 2.4 不参与排名
- garment_position = none 或 other 的衣物
- focus_status ∈ {multi_focus, unclear} 的片段
- 只进入质量排除统计

## 3. 数据模型变更

### 3.1 garment_styles 新增字段
```sql
ALTER TABLE douyin.garment_styles
ADD COLUMN garment_position VARCHAR(16) NOT NULL DEFAULT 'none';
-- 枚举：outer / top / bottom / none
-- none 表示未分类或非衣物，不参与任何排名
```

存量款号迁移时默认 `none`，由运营人工改 `outer/top/bottom`。

### 3.2 video_clips 保留单主衣物语义
- 一段曲线仍归一件衣物（focus_status=clear_primary 的单主衣物语义不变）
- video_clips.style_id + color_id 表示该片段的主要衣物
- garment_position 通过 style_id 关联 garment_styles 派生，不在 clip 上冗余

### 3.3 新增 outfit_combinations 表
```text
outfit_combinations(
  id, account_id, video_id,
  observation_window,
  combination_key,              -- 参与衣物的 (style_id:color_id) 按 garment_position 升序拼接
  participant_count,            -- 参与衣物数（2 或 3）
  annotation_set_hash,          -- 参与片段的规范化 hash
  retention_snapshot_id,
  bounce_snapshot_id_nullable,
  created_at,
  UNIQUE(account_id, video_id, observation_window, combination_key)
)
```

### 3.4 新增 outfit_color_metrics 表
字段口径参照 video_color_metrics，但唯一键改为：
```text
UNIQUE(
  account_id, combination_key, observation_window,
  metric_version, metric_input_hash
)
```

### 3.5 video_color_metrics 保留
单件指标仍存 video_color_metrics，新增 garment_position 派生字段用于分榜筛选：
```sql
ALTER TABLE douyin.video_color_metrics
ADD COLUMN garment_position VARCHAR(16) NOT NULL DEFAULT 'none';
```

## 4. 人工标注入口

### 4.1 前端输入框
标注页提供 3 个独立输入框，纯文字输入（款号+颜色选择器）：
- 外套（outer）
- 上衣（top）
- 裤子（bottom）

每个输入框可留空（表示该视频无该类衣物）。AI 不做识别，全部人工输入。

### 4.2 入口适配
当前只落 3 类衣物位，但数据模型和入口设计需适配未来扩展（可能新增更多衣物位）。garment_position 枚举可扩展，不写死 3 类。

## 5. 保留的 v3.1 约束

- 一个视频片段最多一件主要衣物（clear_primary 单主衣物语义不变）
- multi_focus / unclear 只进入质量排除统计
- 留存与跳出独立选快照、独立计算、独立计数
- 跳出在三视频逐点语义验收前只能叫 platform_bounce_curve_value，不参与任何排名
- 报告只比较同账号、同观察窗口、同位置段
- 64 位作品 ID 全链路字符串
- 不输出 Cookie/JWT/token/签名 URL/验证码

## 6. 删除的 v3.1 约束

- 删除"禁止扩展为整套穿搭"
- 删除"第一版不记录同屏所有衣物"中阻碍多件标注的部分
- 保留"一段曲线不分摊给多件衣物"（单主衣物曲线归属不变）
- 保留"不做自动识别、搭配关系、组合评分、联合归因"（整套只是组合键，不做搭配评分）

## 7. 报告展示

- 报告页提供 3 个独立 Tab：整套穿搭 / 上衣 / 裤子
- 整套穿搭 Tab 在视频具备 ≥2 件合格衣物时才出现样本
- 上衣 Tab 聚合 outer+top
- 裤子 Tab 只含 bottom
- 其他衣物位（none/other）的片段在视频列表可见，但不进入任何排名 Tab

## 8. 对 Task 5 的影响

Task 5 指标计算需分两路：
1. **单件指标**（video_color_metrics）：按 garment_position 分榜，上衣榜=outer+top，裤子榜=bottom
2. **整套指标**（outfit_color_metrics）：同视频 ≥2 件合格衣物聚合

Task 5 的 TDD 需新增：
- garment_position 派生与分榜筛选测试
- outfit_combinations 聚合测试（2件套、3件套、缺外套）
- outfit_color_metrics 计算测试
- 整套 vs 单件指标独立性测试

## 9. 迁移与回滚

- 新增字段和表通过 Alembic 迁移，不动既有数据
- 存量 garment_styles.garment_position 默认 none，运营人工回填
- 回滚：关闭整套排名开关，单件排名仍可用；不删除新表
