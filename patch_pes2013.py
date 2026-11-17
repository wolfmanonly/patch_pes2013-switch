#!/usr/bin/env python3
"""PES2013 on Switch: 改比赛视角(相机表) + 边线清晰度(DXVK 模板与 NRO 哈希)。

用法（在电脑上，对卡里/拷出来的 pes13-fex 目录运行）：

    python patch_pes2013.py "F:\\switch\\pes13-fex"             # 直接改
    python patch_pes2013.py "F:\\switch\\pes13-fex" --dry-run   # 只看会改什么
    python patch_pes2013.py "F:\\switch\\pes13-fex" --no-nro    # 不碰 nro
    python patch_pes2013.py "F:\\switch\\pes13-fex" --restore   # 从 .bak 还原

只改这几处：
    drive_c/PES13/pes2013.exe                       相机表 11 条记录的 2 个 float
    launcher/renderers/dxvk-3.1.1/dxvk.conf         换成 250 字节的调优模板
    pes13-fex.nro                                   目录表里那份模板哈希

改之前每个文件都会留一份同名 .bak（已存在则不覆盖）。不改文件大小，不动游戏数据。
"""

import argparse
import hashlib
import json
import os
import struct
import sys

# ---------------------------------------------------------------- 相机表

REC_SIZE = 76
REC_COUNT = 18
# [1][2][3][4] 是 18 条记录共用的常量，也是定位表头的指纹
FINGERPRINT = struct.pack("<4f", 0.4, 1.0, 0.044, 0.05)
KNOWN_OFFSETS = [(0x10C3CB0, "1.00"), (0x10E00B0, "1.03")]

F_HEIGHT = 12          # [12] 机位高度
F_PITCH = 13           # [13] 俯角, 弧度
EDIT_RECORDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16]

HEIGHT_SCALE = 0.85
PITCH_SCALE = 1.5
PITCH_ADD = 0.10
PITCH_CAP = 0.55

# ---------------------------------------------------------------- DXVK 模板

CONF_SIZE = 250
CONF_BODY = [
    "# Fextendo: VSync ON; LOD -5.0 for pitch lines.",
    "d3d9.maxFrameRate = -1",
    "d3d9.presentInterval = 1",
    "d3d9.maxFrameLatency = 2",
    "d3d9.samplerLodBias = -5.0",
    "d3d9.samplerAnisotropy = 0",
    "d3d9.deviceLocalConstantBuffers = False",
    "dxvk.numCompilerThreads = 1",
]
# 0.4.x 那份原始模板的 sha256，找不到当前模板哈希时用它兜底
ORIG_HASH = b"98bc73015d742b34477466ba1d17cbbb42bad172a7c6fc06266c8eda86121d7d"


def build_conf():
    text = "\n".join(CONF_BODY) + "\n"
    if len(text.encode()) > CONF_SIZE:
        raise SystemExit("模板内容 %d 字节，超过 %d" % (len(text.encode()), CONF_SIZE))
    while len(text.encode()) < CONF_SIZE:
        text += "#\n" if CONF_SIZE - len(text.encode()) >= 2 else "\n"
    data = text.encode()
    assert len(data) == CONF_SIZE
    assert b"d3d9.presentInterval = 1\n" in data
    assert b"d3d9.samplerLodBias = -5.0\n" in data
    return data


def find_table(data):
    """返回相机表起始偏移，找不到返回 None。"""
    idx = data.find(FINGERPRINT)
    while idx >= 4:
        base = idx - 4
        if base + REC_SIZE * REC_COUNT <= len(data):
            return base
        idx = data.find(FINGERPRINT, idx + 1)
    # 兜底：按 float 容差扫（有些版本常量可能不是精确值）
    for off in range(0, len(data) - REC_SIZE * REC_COUNT, 4):
        try:
            v = struct.unpack_from("<4f", data, off + 4)
        except struct.error:
            break
        if (abs(v[0] - 0.4) < 1e-4 and abs(v[1] - 1.0) < 1e-4
                and abs(v[2] - 0.044) < 5e-4 and abs(v[3] - 0.05) < 1e-4):
            return off
    return None


def patch_camera(data, dry):
    base = find_table(data)
    if base is None:
        print("  ! 找不到相机表：这份 exe 不是 1.00/1.03，或已经被别人改过常量。跳过视角。")
        return data, None

    ver = ""
    for off, name in KNOWN_OFFSETS:
        if off == base:
            ver = " (匹配 %s 版)" % name
    print("  相机表在偏移 0x%X%s" % (base, ver))

    buf = bytearray(data)
    rows = []
    for r in EDIT_RECORDS:
        pos = base + r * REC_SIZE
        h, p = struct.unpack_from("<2f", buf, pos + F_HEIGHT * 4)
        if not (1.0 < h < 200.0) or not (-1.0 < p < 1.0):
            print("  ! 记录 %d 的值不像机位（h=%.2f p=%.3f），跳过整份视角修改" % (r, h, p))
            return data, None
        nh = h * HEIGHT_SCALE
        np_ = min(p * PITCH_SCALE, p + PITCH_ADD, PITCH_CAP)
        struct.pack_into("<2f", buf, pos + F_HEIGHT * 4, nh, np_)
        rows.append((r, h, nh, p, np_))

    print("     记录   高度           俯角(rad)")
    for r, h, nh, p, np_ in rows:
        print("     #%-3d  %6.2f → %6.2f   %.3f → %.3f" % (r, h, nh, p, np_))

    diff = sum(1 for i in range(len(data)) if data[i] != buf[i])
    print("  差异 %d 字节" % diff)
    return (data if dry else bytes(buf)), diff


def need_backup(path):
    bak = path + ".bak"
    if os.path.exists(bak):
        print("  (已存在 %s，不覆盖)" % os.path.basename(bak))
        return
    with open(path, "rb") as f:
        data = f.read()
    with open(bak, "wb") as f:
        f.write(data)
    print("  备份 → %s" % os.path.basename(bak))


def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("root", help="pes13-fex 目录，例如 F:\\switch\\pes13-fex")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--no-nro", action="store_true", help="不修改 pes13-fex.nro")
    ap.add_argument("--restore", action="store_true", help="从 .bak 还原后退出")
    ap.add_argument("--force", action="store_true", help="已经改过也再改一次（会叠加缩放，一般不用）")
    a = ap.parse_args()

    root = a.root.rstrip("\\/")
    exe = os.path.join(root, "drive_c", "PES13", "pes2013.exe")
    conf = os.path.join(root, "launcher", "renderers", "dxvk-3.1.1", "dxvk.conf")
    nro = os.path.join(root, "pes13-fex.nro")

    for p in (exe, conf):
        if not os.path.isfile(p):
            raise SystemExit("找不到 %s\n请把路径指到 pes13-fex 这一层（里面应有 drive_c 和 launcher）。" % p)

    if a.restore:
        for p in (exe, conf, nro):
            bak = p + ".bak"
            if os.path.exists(bak):
                with open(bak, "rb") as f:
                    data = f.read()
                with open(p, "wb") as f:
                    f.write(data)
                print("已还原 %s" % p)
        save_state(os.path.join(root, ".patch_state.json"), {})
        return

    print("目录：%s%s\n" % (root, "   (dry-run)" if a.dry_run else ""))

    state_path = os.path.join(root, ".patch_state.json")
    state = load_state(state_path)

    # ---- 1. exe
    print("[1/3] 视角")
    with open(exe, "rb") as f:
        exe_data = f.read()
    exe_sha = hashlib.sha256(exe_data).hexdigest()
    exe_new = exe_data
    exe_diff = None
    if state.get("exe_patched") == exe_sha and not a.force:
        print("  这份 exe 已经改过（和上次输出的 sha256 一致），跳过。")
        print("  想重来先 --restore，或确认了再加 --force。")
    else:
        exe_new, exe_diff = patch_camera(exe_data, a.dry_run)

    # ---- 2. dxvk.conf
    print("\n[2/3] 边线模板")
    with open(conf, "rb") as f:
        conf_old = f.read()
    conf_new = build_conf()
    new_hash = hashlib.sha256(conf_new).hexdigest().encode()
    if conf_old == conf_new:
        print("  已经是调优后的模板，跳过")
        conf_new = None
    elif len(conf_old) != CONF_SIZE:
        print("  ! 现有模板 %d 字节（应为 %d），仍会替换成 %d 字节的标准内容"
              % (len(conf_old), CONF_SIZE, CONF_SIZE))
    if conf_new is not None:
        print("  %d 字节 → %d 字节，新 sha256 %s" % (len(conf_old), CONF_SIZE, new_hash.decode()))

    # ---- 3. nro
    print("\n[3/3] nro 目录哈希")
    nro_new = None
    if a.no_nro:
        print("  按 --no-nro 跳过。注意：不改这里，启动器会判模板被篡改。")
    elif not os.path.isfile(nro):
        print("  ! 没有 %s，跳过" % os.path.basename(nro))
    else:
        with open(nro, "rb") as f:
            nro_data = f.read()
        # 优先用「当前模板的哈希」（版本无关），再退回已知的 0.4.x 原值
        cands = []
        if conf_old:
            cands.append(hashlib.sha256(conf_old).hexdigest().encode())
        cands.append(ORIG_HASH)
        target, pos = None, -1
        for c in cands:
            if c and nro_data.count(c) == 1:
                target, pos = c, nro_data.find(c)
                break
        if target is None:
            print("  ! nro 里没有可唯一定位的模板哈希。")
            print("    可能是别的 FEXTendo 版本。可以先只改模板，再手工处理哈希。")
        elif nro_data.count(new_hash) == 1:
            print("  nro 里已经是新哈希，跳过")
        else:
            buf = bytearray(nro_data)
            buf[pos:pos + 64] = new_hash
            diff = sum(1 for i in range(len(nro_data)) if nro_data[i] != buf[i])
            print("  偏移 0x%X 处替换 64 字符，差异 %d 字节" % (pos, diff))
            nro_new = bytes(buf)

    # ---- 落盘
    if a.dry_run:
        print("\n以上为预览，没有写入任何文件。去掉 --dry-run 即执行。")
        return

    print()
    if exe_diff and exe_new is not exe_data:
        need_backup(exe)
        with open(exe, "wb") as f:
            f.write(exe_new)
        state["exe_patched"] = hashlib.sha256(exe_new).hexdigest()
        save_state(state_path, state)
        print("  已写入 %s" % os.path.basename(exe))
    else:
        print("  视角未改动")

    if conf_new is not None:
        need_backup(conf)
        with open(conf, "wb") as f:
            f.write(conf_new)
        print("  已写入 %s（%d 字节）" % (os.path.basename(conf), CONF_SIZE))

    if nro_new is not None:
        need_backup(nro)
        with open(nro, "wb") as f:
            f.write(nro_new)
        print("  已写入 %s（大小不变）" % os.path.basename(nro))

    print("""
完成。把这三个文件传回卡上，然后：
  · 第一次进游戏会比平时慢，因为 exe 的时间变了，launcher/startup-verified.dat
    失效，启动器会重跑一次全量校验。校验通过后自己会重建，之后恢复正常。
  · 如果这时报 Unreadable or incomplete img/dt03.img，是卡里 img 不完整，
    跟这次改动无关，去查 img。
  · 进比赛看视角有没有变矮、边线有没有变锐。边线没变化先确认 AF 是 0。
  · 想撤回：--restore 会从 .bak 把三个文件都还原。""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
