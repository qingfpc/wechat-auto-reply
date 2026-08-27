# 夜班台 · 微信 PC 拟稿客户端

Windows 专用客户端：打开微信会话，按 `Ctrl+Alt+W`（或在窗口里粘贴对话），生成 2–3 条草稿，**你自己点发送**。

金钱、帮忙承诺、情绪、工作决策只会进待确认队列，客户端不会代发。

## 用户：安装后使用

1. 运行 `dist\夜班台-Setup.exe`（未签名，SmartScreen 可能提示「仍要运行」）。
2. 从开始菜单打开「夜班台」。关闭窗口会缩到托盘，快捷键仍可用。
3. 打开电脑微信，进入要回的会话，按 `Ctrl+Alt+W`。优先读剪贴板；否则 OCR 当前前台窗口。
4. 在夜班台点一条草稿即复制，粘回微信发送。

可选：在「设置」里填写 API Key 和接口地址。不填则走内置规则拟稿。密钥只写在本机 `%APPDATA%\夜班台\user.yaml`，不会打进安装包。

草稿库也在 `%APPDATA%\夜班台\`。卸载程序不会删除这份数据。

## 开发者：源码运行

建议 conda 环境 `wechat-draft-brain`（Python 3.11），不要用系统自带的 3.8。

```powershell
conda env create -f environment.yml
conda activate wechat-draft-brain
pip install -r requirements.txt
python -m wechat_draft_brain
```

或：

```powershell
powershell -File .\scripts\run.ps1
```

会直接弹出夜班台窗口，不再打开浏览器。

也可设置环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`DRAFT_MODEL`（环境变量优先于设置页）。

## 开发者：打 exe 和安装包

```powershell
powershell -File .\scripts\build.ps1
```

会生成：

- 目录版：`dist\NightDesk\NightDesk.exe`（可直接双击）
- 安装包：`dist\夜班台-Setup.exe`（开始菜单、卸载；可选桌面图标和开机启动）

安装包体积主要来自 OCR，大约数百 MB 到 1GB 属正常。需要本机已装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)；脚本找不到时会尝试用 winget 安装。
