# GeoPair Annotator v0.4.0

## 本次更新

- Windows 程序启动后在后台检查 `7paraquat/geopair-annotator` 的 GitHub 最新正式版。无网络时仍可正常标注。
- 发现更高版本后自动下载 Windows ZIP，核对 GitHub Release 附带的 SHA256、ZIP 内版本及逐文件清单。标注页尚未打开时自动更新并重启；标注页已打开时先显示“安装更新”，由标注者保存后点击。
- 保留“选择本地 ZIP 更新”，供离线升级使用。更新仅替换程序文件，保留 `workspace` 和外部数据集。

## 发布要求

自动更新只读取 GitHub **正式 Release**。发布者需推送与 `version.json` 一致的 `vX.Y.Z` tag，仓库的 Windows 构建流程会生成同版 ZIP 和 `.sha256` 并发布 Release。只上传源码或 Actions 构建产物，不会触发自动更新。

## 验证

已用模拟 GitHub Release 测试版本比较、仓库附件 URL、SHA256、ZIP 内容及缺失附件处理，并用隔离目录测试 Windows 程序升级保留 `workspace`。当前 GitHub 只有 v0.1.0，因此现有 v0.4.0 程序启动时不会下载或覆盖自身。
