# GitHub 发布

1. 确定项目名称；当前暂用 GeoPair Annotator。更名时同步 README、窗口标题、EXE 名称、打包脚本和测试中的程序名。名称尚未做重名或商标核查。
2. 查看 README 和 MIT 许可是否符合你的发布意图。检查 `git status`，只提交源码、说明和合成示例。
3. 按 README 在 Windows 上构建、测试、打包。不要从已经标注过的程序目录直接压缩发布。
4. 在自己的 GitHub 账号下新建仓库，推送源码。此项目整理阶段没有创建远程仓库或上传文件。
5. 建立 `v0.1.0` Release，将 `release/GeoPairAnnotator-windows-x64.zip` 和 `.sha256` 文件作为附件上传，普通标注人员下载这个包。

建议仓库描述：Offline optical–SAR paired-image annotation with independent polygons, custom classes, and portable Windows releases.

建议 Topics：`annotation-tool`, `remote-sensing`, `sar`, `semantic-segmentation`, `multimodal`, `offline`, `windows`。

首次发布说明可写：

> 首个 Windows x64 免安装版本。支持光学/SAR 配对查看、独立多边形、可扩展类别、地区进度与标注包导出。原始影像只读，无需 Python 或联网。包含人工合成的界面示例，不包含真实数据集。暂不支持跨电脑自动同步与合并。

保留 `third_party/` 许可文件。不要上传真实数据、工作区、私有清单、服务器信息、日志或未经核实许可的论文插图。自动生成的 `.gitignore` 已覆盖本项目常见输出目录。
