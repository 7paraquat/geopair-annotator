# GeoPair Annotator

**光学与 SAR 配对影像的离线人工标注工具。**

双击 Windows 程序，在浏览器中标注；无需安装 Python，无需联网。支持双模态独立轮廓、可扩展类别、地区进度及标注打包导出。

> 兼容 EarthMiss/EarthM3 风格的文件夹结构，但不是该数据集的官方工具。仓库不提供原始数据集、私人筛选名单或真实人工标注。

## 普通用户怎么用

从仓库的 **Releases** 下载最新版 `GeoPairAnnotator-v*-windows-x64.zip`，完整解压后双击 `GeoPairAnnotator.exe`。不要只复制 EXE，`_internal` 是内置运行环境。v0.4.0 起启动时自动检查 GitHub 正式版；无网络仍可标注。升级细节见 [v0.4.0 更新说明](docs/RELEASE_NOTES_v0.4.0.md)。

1. 点击“选择数据集”，选择直接包含各地区文件夹的目录。
2. 点击“开始标注”，在默认浏览器中打开本地界面。
3. 选择地区和影像，添加类别、绘制多边形；完成后点击网页中的“保存修改”。
4. 交付前先保存，再回启动窗口点击“导出全部已保存标注”，将 ZIP 交回负责人。

下载源码 ZIP 不等于下载免安装程序。首次 Release 尚未发布时，可由维护者按照下方步骤构建。

首次体验可以选择软件包中的 `examples/demo_dataset`。其中的图像是人工生成的几何图案，只用于学习界面，不代表真实 SAR 成像或标注标准。

## 功能

- 光学与 SAR 并排查看，同一对象关联相同标注 ID，两侧轮廓可独立编辑。
- 多边形绘制、顶点调整、撤销/重做、局部放大与中心点定位。
- 道路中线加像素宽度快速生成掩膜，光学和 SAR 可分别调整中线与路宽。
- 圈定区域后用开放或闭合分界线划分地块，逐块赋予类别；三点生成旋转矩形。
- 允许画到图外，保存原尺寸裁剪后的轮廓与掩膜。
- 自定义类别，中文颜色、材质和功能备注。
- 影像状态、地区进度、同一服务中多窗口编辑占用与版本冲突保护。
- 下张影像预加载；原始影像只读取，不自动加载原数据集掩膜。
- 已保存标注恢复；打包导出类别表、标注 JSON、掩膜和历史版本。
- 启动时检查 GitHub 正式版，下载并校验新版；标注中由用户保存后决定安装，离线时可用本地 ZIP 更新。

## 数据格式

```text
dataset/
└── Region-A/
    └── images/
        ├── RGB_png/
        │   └── sample_001.png
        └── SAR_png/
            └── sample_001.png
```

每组光学和 SAR 文件同名、同尺寸，最大 16,777,216 像素。地区名和文件名使用英文字母、数字、横线、下划线或点，不能包含连续两点。使用者可只接收分配给自己的地区。

公开版扫描目录下所有完整配对，不依赖开发者的私有保留名单。半对文件会报错，防止漏发影像后误认为数据完整。原始 TIFF、多波段雷达产品等需要事先制作 PNG 预览；本工具不负责辐射定标或配准。

## 保存与多人离线分工

软件目录下的 `workspace/` 保存配置和标注，移动软件时请一并保留。**绘制后需要点击保存，尚未提交的修改不会进入导出包。**

每个人的工作区独立，不会自动同步到负责人电脑，也不能跨离线电脑判断谁在编辑。建议按地区分工。收到多人的标注包后应分开保管，同图冲突和新增类别的数值 ID 需核对后合并；当前版本没有自动合并功能。

掩膜为原尺寸索引 TIFF；未标像素 `0` 表示忽略，不能直接当作背景负样本。光学/SAR 分别导出时使用 `masks_opt` 和 `masks_sar`。两侧的同一对象 ID 表示语义关联，不表示像素配准。[数据格式说明](docs/DATA_FORMAT.md)

## 从源码运行和构建（开发者）

普通标注人员无需执行本节。开发环境要求 **Windows x64、Python 3.12（包含 Tk）**。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python examples/generate_demo.py
.venv\Scripts\python desktop.py
```

构建与验证：

```powershell
.venv\Scripts\python -m unittest discover -s tests -p "test_dataset_index.py"
.venv\Scripts\python build.py
.venv\Scripts\python tests/test_release.py
.venv\Scripts\python package_release.py
```

结果位于 `release/GeoPairAnnotator-v0.4.0-windows-x64.zip`，附 SHA256 文件。`tests/test_release.py` 使用合成数据测试实际 EXE；`tests/test_update.py` 检查旧包升级保留工作区；`tests/test_github_update.py` 检查 GitHub 更新发现、下载与校验。

源码只公开应用与生成示例；构建产物和个人工作区由 `.gitignore` 排除。二进制包应放到 GitHub Releases，不要提交到 Git 历史。[发布步骤](docs/RELEASING.md)

## 当前范围

- 已在本机 Windows 上执行独立程序测试；尚未验证所有 Windows 环境。
- 程序仅绑定 `127.0.0.1`，不是直接面向互联网部署的多人服务。
- 目前没有模型推理、自动分割、原始雷达产品处理、自动数据对齐或跨机器同步。
- 未做代码签名，Windows 或组织策略可能提示或限制首次运行。

## 许可与依赖

项目自有代码采用 [MIT License](LICENSE)。几何裁剪组件及 Python 依赖保留各自许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。软件许可不授予 EarthMiss 或其他数据集的再分发权限。
