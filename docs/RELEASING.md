# GitHub 发布与自动更新

自动更新只读取公开仓库 `7paraquat/geopair-annotator` 的最新**正式 Release**。源码提交和 Actions 构建产物不会触发用户电脑更新。

1. 更新 `version.json` 和同版 `docs/RELEASE_NOTES_vX.Y.Z.md`，只提交源码、说明和合成示例。不要提交 `workspace`、影像、真实标注或构建目录。
2. 在 Windows 上按 README 运行测试和构建，确认 ZIP 与 `.sha256` 均存在。`tests/test_github_update.py` 验证自动更新协议。
3. 将源码推送到 GitHub `main`。创建并推送与 `version.json` 完全一致的 `vX.Y.Z` tag。
4. GitHub Actions 的 Windows 构建流程会测试、打包并创建正式 Release，附件必须是 `GeoPairAnnotator-vX.Y.Z-windows-x64.zip` 和同名 `.zip.sha256`。
5. 在 GitHub Releases 页面核对版本、附件和构建状态。v0.4.0 及以后安装的程序下次启动会自行发现更高版本并校验更新。

v0.3.0 及更早版本还没有 GitHub 自动检查功能，需先用启动窗口的本地 ZIP 更新入口或按旧版说明手动升级到 v0.4.0。自动更新只替换程序文件，保留 `workspace` 和外部数据集。
