#!/usr/bin/env python3
"""VANTA PSP UI R9 - final polish layer over R8 + Memory Scanner R2."""
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    src = path.read_text(encoding="utf-8")
    if new in src:
        print(f"[skip] {label}")
        return
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}: {path}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"[ok] {label}")


def append_before_class_end(path: Path, class_name: str, code: str) -> None:
    src = path.read_text(encoding="utf-8")
    start = src.find("class " + class_name)
    if start < 0:
        raise RuntimeError(f"class not found: {class_name}")
    open_pos = src.find("{", start)
    if open_pos < 0:
        raise RuntimeError(f"class body not found: {class_name}")
    depth = 0
    state = "code"
    i = open_pos
    while i < len(src):
        ch = src[i]
        nx = src[i + 1] if i + 1 < len(src) else ""
        if state == "code":
            if ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            elif ch == "/" and nx == "/":
                state = "line"; i += 1
            elif ch == "/" and nx == "*":
                state = "block"; i += 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    path.write_text(src[:i] + "\n\n" + code.rstrip() + "\n" + src[i:], encoding="utf-8")
                    return
        elif state == "string":
            if ch == "\\": i += 1
            elif ch == '"': state = "code"
        elif state == "char":
            if ch == "\\": i += 1
            elif ch == "'": state = "code"
        elif state == "line":
            if ch == "\n": state = "code"
        elif state == "block":
            if ch == "*" and nx == "/": state = "code"; i += 1
        i += 1
    raise RuntimeError(f"class end not found: {class_name}")


THEME_HELPER = r'''
    // ==================== VANTA_UI_R9 theme chooser ====================
    private void vantaShowThemeChooser(android.widget.Button source) {
        final String[] ids = {"vanta", "oled", "nebula", "cyber", "crimson"};
        final String[] labels = {"VANTA", "OLED", "NEBULA", "CYBER", "CRIMSON"};
        String current = VantaPrefs.uiTheme(this);
        int selected = 0;
        for (int i = 0; i < ids.length; ++i) if (ids[i].equals(current)) selected = i;
        new android.app.AlertDialog.Builder(this)
            .setTitle("Escolher tema")
            .setSingleChoiceItems(labels, selected, (dialog, which) -> {
                VantaPrefs.setUiTheme(this, ids[which]);
                try { NativeApp.vantaApplyNativeTheme(ids[which]); } catch (Throwable ignored) {}
                dialog.dismiss();
                int oldY = vantaCurrentScrollY(content);
                vantaApplyThemePalette();
                if (currentPage != null) show(currentPage);
                vantaRestoreScrollY(content, oldY);
            })
            .setNegativeButton("Cancelar", null)
            .show();
    }

    private int vantaCurrentScrollY(android.view.View v) {
        if (v == null) return 0;
        if (v instanceof android.widget.ScrollView) return v.getScrollY();
        if (v instanceof android.view.ViewGroup) {
            android.view.ViewGroup g = (android.view.ViewGroup)v;
            for (int i = 0; i < g.getChildCount(); ++i) {
                int y = vantaCurrentScrollY(g.getChildAt(i));
                if (y > 0) return y;
            }
        }
        return 0;
    }

    private void vantaRestoreScrollY(android.view.View v, int y) {
        if (v == null || y <= 0) return;
        if (v instanceof android.widget.ScrollView) {
            android.widget.ScrollView s = (android.widget.ScrollView)v;
            s.post(() -> s.scrollTo(0, y));
            return;
        }
        if (v instanceof android.view.ViewGroup) {
            android.view.ViewGroup g = (android.view.ViewGroup)v;
            for (int i = 0; i < g.getChildCount(); ++i) vantaRestoreScrollY(g.getChildAt(i), y);
        }
    }
    // ================== / VANTA_UI_R9 theme chooser ==================
'''


THEMES = r'''[VANTA]
Name = VANTA
ItemStyleFg = 0xFFFFFFFF
ItemStyleBg = 0x55201946
ItemFocusedStyleFg = 0xFFFFFFFF
ItemFocusedStyleBg = 0xFF6957FF
ItemDownStyleFg = 0xFFFFFFFF
ItemDownStyleBg = 0xFF4B3FD0
ItemDisabledStyleFg = 0x80DDE2F4
ItemDisabledStyleBg = 0x3310182A
HeaderStyleFg = 0xFFB9C3E7
HeaderStyleBg = 0x00000000
InfoStyleFg = 0xFFB9C3E7
InfoStyleBg = 0x00000000
PopupStyleFg = 0xFFFFFFFF
PopupStyleBg = 0xFF11182A
BackgroundColor = 0xFF070B14
ScrollbarColor = 0x706B78A0
PopupSliderColor = 0xFFFFFFFF
PopupSliderFocusedColor = 0xFF6957FF

[VANTA OLED]
Name = VANTA OLED
ItemStyleFg = 0xFFFFFFFF
ItemStyleBg = 0x5510151F
ItemFocusedStyleFg = 0xFFFFFFFF
ItemFocusedStyleBg = 0xFF687AFF
ItemDownStyleFg = 0xFFFFFFFF
ItemDownStyleBg = 0xFF4C5AC0
ItemDisabledStyleFg = 0x80919BB2
ItemDisabledStyleBg = 0x33000000
HeaderStyleFg = 0xFF919BB2
HeaderStyleBg = 0x00000000
InfoStyleFg = 0xFF919BB2
InfoStyleBg = 0x00000000
PopupStyleFg = 0xFFFFFFFF
PopupStyleBg = 0xFF080B12
BackgroundColor = 0xFF000000
ScrollbarColor = 0x708F9AAF
PopupSliderColor = 0xFFFFFFFF
PopupSliderFocusedColor = 0xFF687AFF

[VANTA NEBULA]
Name = VANTA NEBULA
ItemStyleFg = 0xFFFFFFFF
ItemStyleBg = 0x5537205A
ItemFocusedStyleFg = 0xFFFFFFFF
ItemFocusedStyleBg = 0xFF8F7CFF
ItemDownStyleFg = 0xFFFFFFFF
ItemDownStyleBg = 0xFF6C58D0
ItemDisabledStyleFg = 0x80B0A6C9
ItemDisabledStyleBg = 0x33201539
HeaderStyleFg = 0xFFD0C7E7
HeaderStyleBg = 0x00000000
InfoStyleFg = 0xFFD0C7E7
InfoStyleBg = 0x00000000
PopupStyleFg = 0xFFFFFFFF
PopupStyleBg = 0xFF151027
BackgroundColor = 0xFF080611
ScrollbarColor = 0x70B0A6C9
PopupSliderColor = 0xFFFFFFFF
PopupSliderFocusedColor = 0xFF8F7CFF

[VANTA CYBER]
Name = VANTA CYBER
ItemStyleFg = 0xFFF0FFF9
ItemStyleBg = 0x55203835
ItemFocusedStyleFg = 0xFF04100E
ItemFocusedStyleBg = 0xFF35F2D0
ItemDownStyleFg = 0xFFFFFFFF
ItemDownStyleBg = 0xFF22C7A9
ItemDisabledStyleFg = 0x808EB8AD
ItemDisabledStyleBg = 0x33101F1D
HeaderStyleFg = 0xFF8EB8AD
HeaderStyleBg = 0x00000000
InfoStyleFg = 0xFF8EB8AD
InfoStyleBg = 0x00000000
PopupStyleFg = 0xFFF0FFF9
PopupStyleBg = 0xFF0A1B18
BackgroundColor = 0xFF040F0E
ScrollbarColor = 0x708EB8AD
PopupSliderColor = 0xFFF0FFF9
PopupSliderFocusedColor = 0xFF35F2D0

[VANTA CRIMSON]
Name = VANTA CRIMSON
ItemStyleFg = 0xFFFFF4F6
ItemStyleBg = 0x55311820
ItemFocusedStyleFg = 0xFFFFFFFF
ItemFocusedStyleBg = 0xFFFF5D7A
ItemDownStyleFg = 0xFFFFFFFF
ItemDownStyleBg = 0xFFD74762
ItemDisabledStyleFg = 0x80C19AA4
ItemDisabledStyleBg = 0x33211015
HeaderStyleFg = 0xFFC19AA4
HeaderStyleBg = 0x00000000
InfoStyleFg = 0xFFC19AA4
InfoStyleBg = 0x00000000
PopupStyleFg = 0xFFFFF4F6
PopupStyleBg = 0xFF211015
BackgroundColor = 0xFF100609
ScrollbarColor = 0x70C19AA4
PopupSliderColor = 0xFFFFF4F6
PopupSliderFocusedColor = 0xFFFF5D7A
'''


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_vanta_r9.py <PPSSPP-source-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    activity = root / "android/src/org/ppsspp/ppsspp/VantaActivity.java"
    native = root / "android/src/org/ppsspp/ppsspp/NativeApp.java"
    pps = root / "android/src/org/ppsspp/ppsspp/PpssppActivity.java"
    appcpp = root / "android/jni/app-android.cpp"
    tabs = root / "UI/TabbedDialogScreen.cpp"
    pause = root / "UI/PauseScreen.cpp"
    cheat = root / "UI/CwCheatScreen.cpp"
    for path in (activity, native, pps, appcpp, tabs, pause, cheat):
        if not path.is_file():
            raise RuntimeError("missing source: " + str(path))
    if "VANTA_UI_R8" not in activity.read_text(encoding="utf-8"):
        raise RuntimeError("R8 must be applied before R9")
    if "VANTA_MEMORY_SCANNER_R2" not in cheat.read_text(encoding="utf-8"):
        raise RuntimeError("Memory Scanner R2 must exist before R9")

    # Real theme chooser instead of blind theme cycling.
    replace_once(
        activity,
        'android.widget.Button theme=vantaR8Button("TEMA • "+vantaThemeLabel()); theme.setOnClickListener(v->{String c=VantaPrefs.uiTheme(this);String n="vanta".equals(c)?"oled":("oled".equals(c)?"nebula":("nebula".equals(c)?"cyber":("cyber".equals(c)?"crimson":"vanta")));VantaPrefs.setUiTheme(this,n);recreate();});',
        'android.widget.Button theme=vantaR8Button("TEMA • "+vantaThemeLabel()); theme.setOnClickListener(v->vantaShowThemeChooser(theme));',
        "theme submenu",
    )
    if "VANTA_UI_R9 theme chooser" not in activity.read_text(encoding="utf-8"):
        append_before_class_end(activity, "VantaActivity", THEME_HELPER)

    # Apply the launcher-selected theme to native PPSSPP UI too.
    replace_once(
        native,
        "\tpublic static native void vantaApplyOverlayConfig(boolean showFps);",
        "\tpublic static native void vantaApplyOverlayConfig(boolean showFps);\n\tpublic static native void vantaApplyNativeTheme(String themeId);  // VANTA_UI_R9",
        "native theme declaration",
    )
    replace_once(
        pps,
        "        NativeApp.vantaApplyOverlayConfig(VantaPrefs.showFps(this));",
        "        NativeApp.vantaApplyOverlayConfig(VantaPrefs.showFps(this));\n        NativeApp.vantaApplyNativeTheme(VantaPrefs.uiTheme(this));  // VANTA_UI_R9",
        "apply theme inside emulator",
    )
    replace_once(
        appcpp,
        '#include "UI/GameInfoCache.h"',
        '#include "UI/GameInfoCache.h"\n#include "UI/Theme.h"  // VANTA_UI_R9',
        "Theme.h include",
    )
    cpp = appcpp.read_text(encoding="utf-8")
    if "Java_org_ppsspp_ppsspp_NativeApp_vantaApplyNativeTheme" not in cpp:
        cpp += r'''

// ==================== VANTA_UI_R9 native theme bridge ====================
extern "C" JNIEXPORT void JNICALL
Java_org_ppsspp_ppsspp_NativeApp_vantaApplyNativeTheme(JNIEnv *env, jclass, jstring themeId) {
    if (!themeId) return;
    const char *raw = env->GetStringUTFChars(themeId, nullptr);
    std::string id = raw ? raw : "vanta";
    if (raw) env->ReleaseStringUTFChars(themeId, raw);
    if (id == "oled") g_Config.sThemeName = "VANTA OLED";
    else if (id == "nebula") g_Config.sThemeName = "VANTA NEBULA";
    else if (id == "cyber") g_Config.sThemeName = "VANTA CYBER";
    else if (id == "crimson") g_Config.sThemeName = "VANTA CRIMSON";
    else g_Config.sThemeName = "VANTA";
    ReloadAllThemeInfo();
    UpdateTheme();
}
// ================== / VANTA_UI_R9 native theme bridge ==================
'''
        appcpp.write_text(cpp, encoding="utf-8")
    theme_file = root / "assets/themes/vanta_r9.ini"
    theme_file.parent.mkdir(parents=True, exist_ok=True)
    theme_file.write_text(THEMES, encoding="utf-8")
    print("[ok] native VANTA theme pack")

    # Preserve scroll position whenever a settings choice recreates the tab.
    tab_src = tabs.read_text(encoding="utf-8")
    if "VANTA_UI_R9_SCROLL_MEMORY" not in tab_src:
        tab_src = tab_src.replace(
            "#include <algorithm>\n",
            "#include <algorithm>\n#include <map>\n\n// VANTA_UI_R9_SCROLL_MEMORY\nstatic std::map<std::string, float> vantaTabScrollPositions;\n",
            1,
        )
        anchor = "\t\t\tscroll = new ScrollView(ORIENT_VERTICAL, new LinearLayoutParams(FILL_PARENT, FILL_PARENT));\n\t\t\tscroll->SetTag(tag);"
        replacement = anchor + "\n\t\t\t// Keep the exact vertical position after RecreateViews().\n\t\t\tscroll->RememberPosition(&vantaTabScrollPositions[std::string(tag)]);"
        if anchor not in tab_src:
            raise RuntimeError("tab scroll anchor not found")
        tabs.write_text(tab_src.replace(anchor, replacement, 1), encoding="utf-8")
        print("[ok] settings scroll memory")

    # Make Memory Scanner a first-class pause action, right below Continue.
    pause_src = pause.read_text(encoding="utf-8")
    old_cheat = '''\t// VANTA_CHEAT_ENGINE_R1: always expose the cheat panel for real games.\n\tif (PSP_CoreParameter().fileType != IdentifiedFileType::PPSSPP_GE_DUMP) {\n\t\trightColumnItems->Add(new Choice("VANTA CHEATS", ImageID("I_CHEAT")))->OnClick.Add([this](UI::EventParams &e) {\n\t\t\tg_Config.bEnableCheats = true;\n\t\t\tg_Config.bReloadCheats = true;\n\t\t\tscreenManager()->push(new CwCheatScreen(gamePath_));\n\t\t});\n\t}\n'''
    if old_cheat not in pause_src:
        raise RuntimeError("R1 pause cheat block not found")
    pause_src = pause_src.replace(old_cheat, "", 1)
    settings_anchor = "\tif (g_paramSFO.IsValid() && g_Config.HasGameConfig(g_paramSFO.GetDiscID())) {"
    scanner_top = '''\t// VANTA_UI_R9: Memory Scanner stays at the top of the pause menu.\n\tif (PSP_CoreParameter().fileType != IdentifiedFileType::PPSSPP_GE_DUMP) {\n\t\trightColumnItems->Add(new Choice("VANTA MEMORY SCANNER", ImageID("I_CHEAT")))->OnClick.Add([this](UI::EventParams &) {\n\t\t\tg_Config.bEnableCheats = true;\n\t\t\tg_Config.bReloadCheats = true;\n\t\t\tscreenManager()->push(new CwCheatScreen(gamePath_));\n\t\t});\n\t\trightColumnItems->Add(new Spacer(10.0f));\n\t}\n\n'''
    if settings_anchor not in pause_src:
        raise RuntimeError("pause settings anchor not found")
    pause_src = pause_src.replace(settings_anchor, scanner_top + settings_anchor, 1)
    dialog_anchor = "\tstd::string tag = dialog->tag();\n\tif (tag == \"ScreenshotView\") {"
    dialog_new = '''\tstd::string tag = dialog->tag();\n\tif (tag == "CwCheat" && dr == DR_CANCEL) {\n\t\t// Scanner requested a direct return to the running game.\n\t\tfinishNextFrameResult_ = DR_BACK;\n\t\tfinishNextFrame_ = true;\n\t\treturn;\n\t}\n\tif (tag == "ScreenshotView") {'''
    if dialog_anchor not in pause_src:
        raise RuntimeError("pause dialog anchor not found")
    pause.write_text(pause_src.replace(dialog_anchor, dialog_new, 1), encoding="utf-8")
    print("[ok] scanner promoted in pause menu")

    # Direct Resume Game button inside the scanner; scan session remains static/alive.
    cheat_src = cheat.read_text(encoding="utf-8")
    scanner_anchor = '''\t// VANTA R2 native scanner settings. The old "Search" below still filters cheat *names*.\n    leftColumn->Add(new ItemHeader("VANTA MEMORY SCANNER R2"));'''
    scanner_new = '''\t// VANTA R2 native scanner settings. The old "Search" below still filters cheat *names*.\n    leftColumn->Add(new ItemHeader("VANTA MEMORY SCANNER R2"));\n    leftColumn->Add(new Choice("▶ RESUME GAME"))->OnClick.Add([this](UI::EventParams &) {\n        std::lock_guard<std::recursive_mutex> guard(MIPSComp::jitLock);\n        if (MIPSComp::jit) MIPSComp::jit->ClearCache();\n        TriggerFinish(DR_CANCEL);\n    });'''
    if scanner_anchor not in cheat_src:
        raise RuntimeError("scanner header anchor not found")
    cheat.write_text(cheat_src.replace(scanner_anchor, scanner_new, 1), encoding="utf-8")
    print("[ok] scanner direct RESUME GAME")

    print("[ok] VANTA UI R9 applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
