# PES2013 on Switch：改视角与边线

在 Switch 上通过 FEXTendo 兼容层跑 PC 版《实况足球 2013》，改比赛视角、边线清晰度。下面写的是具体改哪个文件、改成什么值。


适用环境：PES2013 1.00（`pes2013.exe` 19,969,024 字节）· FEXTendo 0.4.2（PES13-NX）· emuMMC

两处改动都不在游戏数据包里：视角在 exe，边线在 dxvk.conf。


## 不想手动改：跑脚本

`patch_pes2013.py` 一个文件，不装第三方库，Python 3.8 以上可用。不过更建议直接AI

```
python patch_pes2013.py "F:\switch\pes13-fex"            直接改
python patch_pes2013.py "F:\switch\pes13-fex" --dry-run  只看会改什么，不写文件
python patch_pes2013.py "F:\switch\pes13-fex" --restore  从 .bak 还原
```

它会按 `[1][2][3][4]` 那组常量定位相机表，对不上就跳过视角、不动 exe；把 11 条记录的机位高度 ×0.85、俯角按 `min(×1.5, +0.10, 0.55)` 写进去（实测差异 69 字节）；把 dxvk.conf 换成 250 字节的调优模板；在 nro 里找到模板哈希，换成新的。每个文件改之前留一份 `.bak`。

跑完把三个文件传回卡，第一次进游戏会重验一遍，原因见第二节末尾。

脚本会在目录里写一个 `.patch_state.json` 记住改过的 exe，重复跑会跳过，免得视角被乘两次。想只改模板不动 nro，加 `--no-nro`（那样启动器会判模板被篡改）。

## 一、先把卡连上电脑

Switch 上进相册 → hbmenu → DBI → `Run FTP server`，屏幕会显示 `ftp://192.168.x.x:5000`，用户名 `anonymous`，密码空，根目录就是 SD 卡。

别用 `Run MTP responder`，那个只能手动拖文件，AI 读不到。

连上后确认这三个文件在：

```
/switch/pes13-fex/drive_c/PES13/pes2013.exe
/switch/pes13-fex/pes13-fex.nro
/switch/pes13-fex/launcher/renderers/dxvk-3.1.1/dxvk.conf
```

## 二、视角：改 exe 里的相机表

改 `/switch/pes13-fex/drive_c/PES13/pes2013.exe`。

1.00 版的表在偏移 `0x10C3CB0`，18 条，每条 76 字节（19 个 float）。

每条里只有两个字段要改：

- `[12]` 机位高度，改成原值 × 0.85。Wide 机位是 14.21 → 12.08。
- `[13]` 俯角（弧度），改成 `min(原值 × 1.5, 原值 + 0.10, 0.55)`。单条最多抬 5.7°，封顶 0.55 rad；再高会看到场外和穿地。

只改这 11 条：0~8、12、16。9~11 是俯角为负大数的异常记录，13~15 是电影机位，17 是垃圾数据（`[12]` = 3584），都不要碰。

`[0]`~`[10]` 是全表共用的常量，动一个游戏就崩。

改完整个文件只有 69 字节不同，超了就说明位置错了。

版本不是 1.00 时表的位置会变（1.03 在 `0x10E00B0`）。不用记偏移，搜 `[1][2][3][4]` ≈ 0.4 / 1.0 / 0.044 / 0.05 这一组，18 条都一样，很好认。

网上那个 2013 年的 3DMGAME 视角工具给的是 `0x10C3D7E`，别抄：那个位置不在记录边界上，而且它那版字段是单字节，这里是 float。

### 改完要更新启动器的校验文件

改 exe 后文件时间变了，`launcher/startup-verified.dat`（976 字节）里记的「大小 + 时间」就对不上，启动器会重跑全量校验，然后报 `Installation is not correct. Unreadable or incomplete img/dt03.img`。这个报错跟 exe 内容无关。

这个文件从 `0x360` 开始是 7 组 `<u64 大小, u64 时间>`，顺序是：exe、img 目录、system32/ntdll、system32/libwow64fex、syswow64/ntdll、launcher/font.bin、launcher/wordmark.rgba。按卡上这 7 个文件实际的大小和时间重写一遍就行。

注意要在文件传到卡上之后再读时间，本地算好再传等于白算。

## 三、边线：改 dxvk 模板

改 `/switch/pes13-fex/launcher/renderers/dxvk-3.1.1/dxvk.conf`。

卡上有三个 dxvk.conf，只有这份是模板。`launcher/presets/dxvk.conf` 和 `drive_c/PES13/dxvk.conf` 每次启动都会被模板覆盖，改它们重启就没了，也没有任何提示。

整份内容（必须正好 250 字节，差多少用 `#` 注释行补）：

```
d3d9.maxFrameRate = -1
d3d9.presentInterval = 1
d3d9.maxFrameLatency = 2
d3d9.samplerLodBias = -5.0
d3d9.samplerAnisotropy = 0
d3d9.deviceLocalConstantBuffers = False
dxvk.numCompilerThreads = 1
```

关键是 `samplerLodBias = -5.0` 和 `samplerAnisotropy = 0` 这两行；`presentInterval = 1` 要留着，渲染器检查会看。

### 改完要更新 nro 里的哈希

这份模板的 sha256 登记在启动程序 `pes13-fex.nro`（32,059,753 字节）的目录表里。模板内容变了、哈希没跟着变，启动器直接判篡改。

在 nro 里搜这段 64 个字符：

```
98bc73015d742b34477466ba1d17cbbb42bad172a7c6fc06266c8eda86121d7d
```

整串替换成新模板的 sha256（同样 64 个 ASCII 字符）。nro 总大小不变，只有 63 个字节不同。

别记偏移（这一版是 `0x11c8ab0`，换 FEXTendo 版本就变），直接搜这串。搜到多处或者一处都搜不到，就停手别改。

`pes13-fex.nro` 是游戏启动程序（32 MB），不是装引导层补丁的 `FEXTendo-Patch.nro`，别搞混。

### 没效果的话

先确认 AF 是 0。开着各向异性过滤时，LOD bias 从 −0.5 一路加到 −2.5 都看不出边线变化，因为 AF 会把 LOD 的效果平均回去。代价是轻微摩尔纹。

## 四、备份

动手前先把这几个文件整份下载到电脑存一个目录：

- `pes2013.exe` 19,969,024 B
- `pes13-fex.nro` 32,059,753 B
- `launcher/renderers/dxvk-3.1.1/dxvk.conf` 250 B
- `launcher/startup-verified.dat` 976 B

传回卡之后整份回读 sha256，别只看大小。截断过的文件顶着正确文件名照样躺着，进游戏直接卡死，报错完全指不到原因。

也可以让 AI 在每个文件的同目录 `cp` 一份 `.bak`，回滚时改回来比重下快。

## 五、可以直接粘给 AI 的话

不懂怎么下手的话，把下面整段连地址一起发给能改文件的 AI，它会自己找位置：

> 我的 Switch 用 DBI 开了 FTP：地址 192.168.x.x:5000，用户名 anonymous、密码空，根目录就是 SD 卡（sdmc:）。帮我改 PC 版 PES2013（1.00）的视角和边线，三个文件都在卡上：
>
> - /switch/pes13-fex/drive_c/PES13/pes2013.exe（19,969,024 字节）
> - /switch/pes13-fex/pes13-fex.nro（32,059,753 字节）
> - /switch/pes13-fex/launcher/renderers/dxvk-3.1.1/dxvk.conf（250 字节）
>
> 动手前先把这三个文件整份下载到电脑本地一个备份目录（电脑上本来没有原件），并记下各自的 sha256。
>
> ① 视角：pes2013.exe 偏移 0x10C3CB0 起是相机表，18 条 × 76 字节、每条 19 个 float。只改记录 0~8、12、16 的 [12] 机位高度 ×0.85 和 [13] 俯角弧度取 min(原值×1.5, 原值+0.10, 0.55)；[0]~[10] 是全表共用常量，不能动。改完只应有约 69 字节差异。版本不是 1.00 就用 [1][2][3][4]≈0.4/1.0/0.044/0.05 扫表头定位（1.03 在 0x10E00B0）。传回卡之后，再用 FTP 的 MDTM 读卡上 exe 的实际 size/mtime，重建 /switch/pes13-fex/launcher/startup-verified.dat（976 字节，锚点自 0x360 起 7 组 u64 size+mtime），否则启动器会重跑全量校验、报 img 损坏。
>
> ② 边线，模板和 nro 两个都要动：
>
> a) /switch/pes13-fex/launcher/renderers/dxvk-3.1.1/dxvk.conf 是模板（drive_c/PES13 和 launcher/presets 下那两份每次启动会被模板覆盖，改它们无效），加 d3d9.samplerLodBias = -5.0 与 d3d9.samplerAnisotropy = 0，保留 d3d9.presentInterval = 1，整份必须正好 250 字节（差多少用 # 注释行补）；
>
> b) 这份模板的 sha256 登记在 pes13-fex.nro 的目录表里，模板内容一改哈希就对不上，启动器直接判篡改。所以要在 nro 里搜那串 64 字节 ASCII 十六进制 98bc73015d742b34477466ba1d17cbbb42bad172a7c6fc06266c8eda86121d7d，整串替换成新模板的 sha256（同样 64 字节 ASCII）；nro 总大小不变，应只改动 63 个字节，搜到多处或搜不到就停手别改。
>
> 改完把三个文件传回卡，整份回读 sha256 与本地一致才算完。

## 说明

- 文中的偏移、字节数和 sha256 片段都来自 1.00 版实测。版本不同位置会变，认不准就先扫表头，别硬改。
- 改任何文件之前先备份整份原件。这些文件都在 SD 卡上，电脑上一般没有。
- 只用于单机自己玩，别拿去联机。
