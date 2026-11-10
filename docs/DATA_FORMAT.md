# 标注数据

运行后在 `workspace/` 创建：

```text
workspace/
├── config.json                  # 本机数据集路径，不应上传仓库
├── identity.json                # 本份工作区的独立 ID
├── selected.json                # 扫描生成的样本清单
└── state/
    ├── custom_categories.json   # 通过界面新增后创建
    ├── custom_attributes.json   # 通过界面新增后创建
    └── reviews_shared/
        ├── label_map.json
        └── EarthMiss--Region-A/
            ├── ...             # 当前记录和每次保存的版本
            └── _revisions/
```

`EarthMiss--` 是兼容既有保存协议的内部地区前缀，不代表数据来源经过官方认证。

每条记录关联 `site`、`stem`、`image_size`、`revision`、`workflow_status`、`geometry_mode`、`annotations`、`label_map`。单个对象的 `polygon` 和 `sar_polygon` 分别使用各自影像像素坐标；对应 `segmentation` 和 `sar_segmentation` 使用 COCO RLE。颜色、材质、功能备注保存在对象属性中。

`opt_keep=false` 或 `sar_keep=false` 表示该侧尚未确认轮廓，不能当作“地物确定不存在”。同一标注 ID 连接两侧对象，工具不会移动原影像或替你完成配准。

保存采用不可变版本目录，再原子更新当前记录；旧的 `base_revision` 被拒绝，避免静默覆盖。网页的单图导出提供掩膜和记录；启动器的全部导出则是完整交付快照，带工作区 ID 和逐文件 SHA256，排除编辑占用数据库、影像和临时文件。

收到多个交付包时先按工作区 ID 分开存放。不同工作区可能给同一个新增类别分配不同像素编号，因此应按类别语义核对类别表并重新映射，不能只拼接 TIFF 或直接覆盖同名 JSON。
