# 小应校园 · 静态改包工具集

对 **小应校园**（`life.mysit.sit_life`，上海应用技术大学校园 App，Flutter 3.11.5 / Dart AOT）做**纯静态 ARM64 指令级补丁**的工具链与逆向笔记。

不注入、不挂 Frida、不联网拦截——直接改 `lib/arm64-v8a/libapp.so` 里的机器码，重打包重签，装上去就是改好的样子。

> 本项目**只含**补丁脚本与文档。不含 APK、不含反编译产物、不含任何签名密钥。

---

## 它改了什么

| 改动 | 效果 |
|---|---|
| 底部导航 5 → 3 | 只保留 `课表 / 校园 / 我的`，去掉「广场」「消息」 |
| 根路由重定向 | 启动直接落在课表，不再进广场 |
| 校园页精简 | 去掉顶部公告栏（含「推荐 / 公告 / 校园」切换条与广告位）、「小应」分组、「应援计划」分组 |
| 校园页宫格 | 只留 6 项：校园一卡通 / 充值校园卡 / 宿舍电费 / 考试成绩 / 考试安排 / 绩点计算器 |
| 修「导入课表失败」 | 教务周次字段变成 `第18` 后解析崩溃，补丁让映射器丢弃 `第` 字 |

---

## 原理速览

Flutter release 包没有 JIT，业务逻辑全在 `libapp.so` 的 Dart AOT 快照里，jadx 只能看到 Java 壳。

好在**这个 App 没有做符号混淆**：`libapp.so` 里保留了 3441 个 `package:...` 源文件路径、类名、字段名。于是可以：

1. **blutter** 把 `libapp.so` 还原成带符号的 ARM64 反汇编（`asm/<package>/<file>.dart`）+ 对象池（`pp.txt`）
2. 在反汇编里定位到目标函数，读到精确的 `vaddr`
3. 用 ELF 段表把 `vaddr` 换算成文件偏移
4. **改 4 字节指令**：改长度常量、改池偏移、把调用改成 NOP、把条件跳转改成无条件跳转
5. 用 capstone 反汇编改后的字节做回归验证
6. 把 `libapp.so` 塞回 APK（保持 stored + 4K 对齐），`apksigner` 重签

详见 [`docs/patch-map.md`](docs/patch-map.md)（每个补丁的地址、原指令、依据）和 [`docs/reversing-notes.md`](docs/reversing-notes.md)（方法论与坑）。

---

## 快速开始

```bash
# 0) 准备：从你自己的设备取出 base.apk
adb shell pm path life.mysit.sit_life          # 得到 base.apk 路径
adb pull /data/app/.../base.apk

# 1) 还原符号（需要 blutter：https://github.com/worawit/blutter）
python3 blutter.py path/to/lib/arm64-v8a out_dir

# 2) 打补丁
python3 patch_libapp.py libapp.so libapp_patched.so

# 3) 塞回 APK（保持 libapp.so 为 stored）
python repack.py base.apk libapp_patched.so modded_nosign.apk
zipalign -p -f 4 modded_nosign.apk modded_aligned.apk
apksigner sign --ks <your.keystore> --out modded.apk modded_aligned.apk

# 4) 安装（签名与原版不同，需先卸载原版）
adb install -r modded.apk
```

`week_parse_model.py` 是把周次解析逻辑按反汇编如实还原的可执行模型，用来离线验证格式覆盖，不需要真机：

```bash
python3 week_parse_model.py
```

---

## 补丁表

完整表格见 [`docs/patch-map.md`](docs/patch-map.md)。摘要：

| # | 地址 | 原始 | 补丁 | 作用 |
|---|---|---|---|---|
| A1–A6 | `0xe03d8c`…`0xe03db8` | `ldur/stur` 序列 | 改池偏移 + NOP + 长度 `0xa`→`0x6` | 底部导航 5 → 3 |
| B1–B6 | `0xd64ae0`…`0xd64b14` | 同上 | 同上 | 路由分支 5 → 3 |
| C1 | `0xd64ee0` | `ldr [x0,#0x9b8]` | `#0x998` | 根路由 `/social` → `/timetable` |
| D1 | `0xe0bc90` | `b.eq` | `b` | 不合并服务端 portal |
| D2/D3 | `0xd66040`,`0xdaa804` | `movz #0x6` / `#0x2` | `#0x0` | 清空本地「小应」分组 |
| D4 | `0xdb139c` 等 5 处 | `ldr` hookId | 指向「绩点计算器」 | 靠去重丢掉 5 个宫格项 |
| D5 | `0xe0aa0c` | `movz #0x4` | `#0x2` | 去掉公告栏 sliver |
| E1–E3 | `0x16a8918`,`0x16a8964`,`0x16a8974` | 阈值 `U+3010` / 写 `[` | 阈值 `U+7B2C` / 跳不输出 | 丢弃「第」字 |

---

## 版权与免责

* 本项目**不包含**任何第三方 App 的二进制或反编译产物。所有补丁都以「地址 + 指令」形式描述，需要使用者自行从**自己所持设备**取出 APK 并还原。
* `libapp.so`、`base.apk`、blutter 输出、签名密钥、日志与截图均不随仓库分发（见 `.gitignore`）。
* 修改后的 App 不可再用于官方渠道分发；由此产生的任何后果由使用者自行承担。
* 代码以 MIT 协议开源。

## License

MIT — 见 [`LICENSE`](LICENSE)。
