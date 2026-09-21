# Jev Arena — System One 模型实战对比场

让 **Jev**（TypeSafe 云端 API）、**NanoJev**（0.6B 本地权重）、**Laya**（421M 本地权重）在
**俄罗斯方块** 和 **1024** 上用完全相同的问题序列对局，录制每一步的选择与概率分布，
在参考 [nanojev 展示站](https://nanojev.tianyuchen99.chatgpt.site/) 风格的三面板回放页中同步播放。

## 🎬 对比视频

**Tetris**：

**1024** ：

> 左 Jev（云 API）· 中 NanoJev（0.6B 本地）· 右 Laya（421M 本地）。

## 📊 最终战绩（v4 协议：策略层级指令 + fan-out + 组合评分）

### Tetris（10×20，朝向×列组合动作，80 块预算）

| 引擎 | seed 2026 | seed 901 | 说明 |
|---|---|---|---|
| **Jev** | **1900 分 / 17 消行 / 80 块打满** | **1280 分 / 26 消行 / 80 块打满** | seed901 终局仅 60 格填充、列高 4-9（真正的低矮平整形态） |
| NanoJev | 0 分 / 29 块 | 0 分 / 26 块 | 全程真实模型决策（1024-token 上限），朝向使用 4/4 |
| Laya | 0 分 / 22 块 | 0 分 / 27 块 | one-hot 分布撑不起 17-34 选项空间 |

### 1024（标准 2048 规则，4×4）

| 引擎 | seed 2026 | seed 901 | 终局形态 |
|---|---|---|---|
| **Jev** | **1788 分 / 128** | **1564 分 / 128** | 降幂蛇形（128,64,32,16/8,32,16,8/...）= 标准高手形态 |
| Laya | 1072 / 128 | 1596 / 128 | 满盘碎块 |
| NanoJev | 644 / 64 | 600 / 64 | 早期卡死 |

### 决策延迟（每步）

Jev API ~1.16s（含 choice+noul fan-out 单次调用）· NanoJev ~0.3-1.8s（GPU1 共享）· Laya ~0.1s

## 🚀 快速开始

```bash
# 1. 录制对局（需要 .env 里的 TYPESAFE_API_KEY；nanojev/laya 走本地 venv）
python runner/run_matches_v3.py          # 断点续跑，schema jev-arena-v3

# 2. 打开回放站
cd web && python -m http.server 8775
# 浏览器打开 http://127.0.0.1:8775  （#tetris 直达俄罗斯方块）

# 3. 验证
python test_games.py                     # 游戏引擎单测（7 项）
python test_tetris_v2.py                 # 旋转引擎单测（6 项）
python replay_check.py                   # 12 局录像逐一回放一致性校验
python verify_site.py                    # Playwright 站点验证（8 项断言）
python record_videos.py                  # 录制对比视频（webm → 手动转 mov）
```

## 🎯 对局协议（公平性 + 官方最佳实践）

每步对三引擎发送**逐字节相同**的请求，遵循 TypeSafe 官方文档与 NanoJev 作者实践：

1. **策略层级指令**：Tetris"①消行②防洞③列低且均匀（sum/max/bumpiness），平局等价"；1024"①合并分②大合并③空格"
2. **选项描述带真实后果**：每个落点/方向附消行数、洞数变化、高度和/起伏度（Dellacherie 特征）
3. **Fan-out**：choice + noul 风险门一次调用并行（官方 12x 便宜/10x 快）
4. **组合评分**：argmax 为主；margin<0.05 且 noul 门触发时代码端确定性重排
5. **唯一合法动作代码直接执行**（不耗模型调用）
6. **按引擎适配状态渲染**：nanojev 用 compact 状态（512 训练上限→1024 推理上限已验证骨干支持 40960）

历史版本录像：`web/arena_results_v{1,2,3}.json`（含 v1 中性协议、v2 旋转动作、v3 首版最佳实践）。

## 📁 目录结构

```
jev-arena/
├── games/
│   ├── tetris.py / tetris_v2.py   # 列选择版 / 朝向×列组合版（20 行标准棋盘）
│   └── game1024.py                # 标准 2048 生成规则（每次有效移动生成新块）
├── runner/
│   ├── engines.py / engines_multi.py   # 单问题 / fan-out 多问题适配器
│   ├── nanojev_worker.py / laya_worker.py  # 行协议子进程（独立 venv）
│   ├── protocol_v3.py             # 策略层级指令 + 状态渲染 + 组合评分
│   ├── run_matches_v3.py          # 对局录制（断点续跑、增量落盘）
│   └── smoke*.py                  # 冒烟测试
├── web/                           # 纯静态三面板回放站（vanilla HTML/CSS/JS）
├── docs-media/                    # 对比视频 .mov（README 引用）
├── shots/                         # Playwright 截图证据
├── test_games.py / test_tetris_v2.py
├── replay_check.py                # 录像回放一致性校验（作者同款思路）
├── verify_site.py                 # 站点 8 项断言
├── ACCEPTANCE.md → ACCEPTANCE_V4.md   # 四轮验收报告（含弯路复盘）
└── .env                           # TYPESAFE_API_KEY / TYPESAFE_MODEL（不入库）
```

## 📜 四轮迭代史（详见各轮 ACCEPTANCE）

| 轮次 | 主题 | 关键发现 |
|---|---|---|
| v1 | 基线：同题对局 + 回放站 | 选项描述必须带真实后果数据，纯方向词=测措辞敏感度 |
| v2 | 旋转动作空间 + 行为指标 | 组合动作空间放大强模型领先（40→340 分） |
| v3 | 官方最佳实践（层级/fan-out/组合评分） | **揪出 1024 规则 bug**（合并才生成新块）→ jev 4→2444 分；"三家都烂先查环境" |
| v4 | Tetris 几何 + 平坦度（用户反馈驱动） | 14→20 行 + Dellacherie 特征 → jev 1590 均分；nanojev 512-token 静默降级坑 |

## 致谢与参考

- 风格与交互范式参考 [NanoJev side-by-side 展示站](https://nanojev.tianyuchen99.chatgpt.site/)（Tianyu Chen，源码在本地 `F:\Space\PRO\test\nanojev\NanoJev\web\`）
- [TypeSafe Jev 文档](https://docs.typesafe.ai/introduction) · [NanoJev](https://github.com/TianyuCodings/NanoJev) · [laya](https://huggingface.co/convaiinnovations/laya)
