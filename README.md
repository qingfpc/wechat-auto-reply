# 夜班台 · 微信拟稿大脑

两种模式可随时切换：

- **快捷键拟稿**：把微信窗口置于前台，按 `Ctrl+Alt+W`（或在页面里粘贴对话），生成 2–3 条草稿，你自己发送。
- **OCR+ADB 全自动**：用 ADB 截手机屏，OCR 找未读红点，点进会话，拟稿后按策略决定是否发送。

金钱、帮忙承诺、情绪、工作决策 **即使全自动也不会发出去**，只会进待确认队列。

## 环境

建议使用 conda 环境 `wechat-draft-brain`（Python 3.11）：

```powershell
conda env create -f environment.yml
conda activate wechat-draft-brain
python -m wechat_draft_brain.app
```

或直接：

```powershell
powershell -File .\scripts\run.ps1
```

浏览器打开 http://127.0.0.1:8765

可选：设置 `OPENAI_API_KEY`（以及可选的 `OPENAI_BASE_URL`、`DRAFT_MODEL`）。不设则走内置规则拟稿。

## 快捷键拟稿

1. 打开电脑微信，进入要回的会话。
2. 按 `Ctrl+Alt+W`。优先读剪贴板；否则 OCR 当前前台窗口。
3. 在夜班台点一条草稿即复制，粘回微信发送。

## OCR+ADB 全自动

本机当前 **PATH 里没有 adb**。需要：

1. 安装 [Android platform-tools](https://developer.android.com/tools/releases/platform-tools)，把 `adb.exe` 所在目录加入 PATH，或把完整路径填进 `config/default.yaml` 的 `adb.path`。
2. 手机打开开发者选项与 USB 调试，用数据线授权这台电脑。
3. 微信停留在 **聊天列表**。锁屏、分屏、键盘弹起都会让 OCR 变差。
4. 要发中文，建议手机安装 [ADB Keyboard](https://github.com/senzhk/ADBKeyBoard) 并切到该输入法。
5. 页面切到「OCR+ADB 全自动」。默认 **空跑**：只拟稿、不点发送。
6. 只有同时关闭「空跑」并勾选「解除保险」，寒暄/事务确认才会真的发出去。

个人微信没有官方机器人接口，全自动仍有封号风险。这是截屏+点击，不碰微信进程内部。

## 模式怎么切

页面顶部两个按钮随时切换。切到全自动会二次确认。切回拟稿会自动带上保险。
