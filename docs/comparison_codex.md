# IntentForge vs Codex — 侧面对比实验

## 同一条指令

```
Make a wall-mounted bracket 120mm wide, 80mm tall, 6mm thick,
with two horizontal symmetric mounting holes and optional center cutout
```

## 对比维度

| 维度               | IntentForge                                                                       | Codex (通用 LLM)            |
| ---------------- | --------------------------------------------------------------------------------- | ------------------------- |
| **输出格式**         | 结构化 intent JSON + 参数 YAML + 约束图 + feature plan + STEP/STL                         | 单次 CadQuery/Python 脚本     |
| **参数命名**         | 每个维度有 name + unit + source + reason + locked + min/max                            | 硬编码数字，无命名语义               |
| **设计意图记录**       | assumptions (7项), unknowns (5项), feature_flags (4项含 reason/state)                 | 无                         |
| **默认值可追溯**       | hole_diameter=5mm (标注 source:default, reason:"Controls screw clearance")          | 数字出现在代码里，无来源说明            |
| **feature flag** | mounting_holes / center_cutout / rounded_corners / edge_fillets 各有 state + reason | 无 feature flag，功能隐含在代码流程中 |
| **验证**           | 12 项 geometry checks，每项有 expected/actual/tolerance/related_parameters             | 无内置验证                     |
| **编辑**           | "Make it 150mm wide but keep the same thickness" → 只改 width，preserve thickness    | 需要重新生成整个脚本，不保持上次的意图       |
| **编辑后约束传播**      | 间距、cutout 尺寸自动重新推导（derived source）                                                | 手动修改所有相关数字                |
| **可回溯性**         | run_id + request_id + persistent artifact 目录                                      | 无持久追踪                     |
| **确定性**          | 同一 prompt 100% 相同输出                                                               | 不同 run 可能产生不同代码结构         |

## 给 Codex 的 Prompt（直接复制使用）

### Prompt A：初次生成

```
Write a CadQuery Python script that creates a wall-mounted bracket:
- 120mm wide, 80mm tall, 6mm thick rectangular back plate
- Two symmetric horizontal mounting holes (diameter 5mm, spacing 80mm)
- A centered rectangular cutout (42mm wide, 24mm high)
Export to STEP and STL.
```

### Prompt B：编辑修改（对比 IntentForge 的编辑保持能力）

```
Modify the previous CadQuery script: change the width to 150mm,
but keep the same thickness (6mm) and hole diameter (5mm).
The hole spacing and cutout dimensions should update accordingly.
```

### Prompt C：不支持场景（对比 IntentForge 的结构化拒绝）

```
Write a CadQuery Python script for a gear with 20 teeth,
inner diameter 30mm, outer diameter 60mm, tooth height 15mm.
```

## 对比检查清单

跑完 Codex 的输出后，逐项检查：

### 初次生成 (Prompt A)

1. ✅/❌ 几何是否正确？(120×80×6mm, 2 孔, 1 切口)
2. ✅/❌ 参数是否命名且有语义？(不是 `120` 而是 `back_plate_width_mm`)
3. ✅/❌ 是否记录了假设和未知？(如 "hole diameter defaulted to 5mm")
4. ✅/❌ 是否有 feature flag？(可以关闭 center_cutout 而不改代码结构)
5. ✅/❌ 是否有验证报告？(bounding box match, hole clearance, cutout inside plate)
6. ✅/❌ 默认值来源是否可追溯？(5mm 来自什么决策？)

### 编辑修改 (Prompt B)

1. ✅/❌ 编辑是否只改目标参数？(只改 width，thickness/hole_diameter 不变)
2. ✅/❌ 衍生参数是否自动更新？(spacing, cutout 随 width 变化)
3. ✅/❌ 是否保持原始设计意图？(feature flag 状态不变)
4. ✅/❌ 是否有编辑对比报告？(before → after 参数 diff)

### 不支持场景 (Prompt C)

1. ✅/❌ 是否明确拒绝并说明原因？(IntentForge: ToolError + error_type + recoverable)
2. ✅/❌ 是否给出可恢复建议？(suggest what IS supported)

## IntentForge 产物文件

| 文件                              | 内容                                                               |
| ------------------------------- | ---------------------------------------------------------------- |
| `parsed_intent.json`            | 结构化意图：family, requirements, assumptions, unknowns, feature_flags |
| `parsed_params.yaml`            | 参数表：8 个命名参数，含 source/reason/min/locked                           |
| `parsed_constraints.json`       | 约束图：参数间关系                                                        |
| `parsed_feature_plan.json`      | Feature plan：每步含 feature + reason                                |
| `parsed_validation_report.json` | 12 项验证：每项含 expected/actual/tolerance/related_params              |
| `parsed_bracket.step`           | STEP 导出 (40KB)                                                   |
| `parsed_bracket.stl`            | STL 导出 (52KB)                                                    |
| `parsed_edit.json`              | 编辑意图：set_parameter width=150, preserve thickness                 |
| `updated_params.yaml`           | 编辑后参数：width=150, 其他不变                                            |
| `edited_validation_report.json` | 编辑后验证：12/12 passed                                               |

## 核心差异总结

**IntentForge** 不是 "text-to-CAD"。它是 "intent-preserving CAD pipeline"。

Codex 类工具生成的是一次性代码——能用，但不可编辑、不可追溯、不可验证。  
IntentForge 生成的是可编辑的参数化模型——每个数字有名字、有来源、有约束、有验证，  
编辑只改目标参数，其余自动传播，完整记录每一次变更的理由。

这就是 "看起来对了" 和 "工程上对了" 的区别。

