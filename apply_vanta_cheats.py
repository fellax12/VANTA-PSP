#!/usr/bin/env python3
from pathlib import Path
import sys

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[skip] {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ok] {label}")

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_vanta_cheats.py <ppsspp-root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    cheat_cpp = root / "UI" / "CwCheatScreen.cpp"
    pause_cpp = root / "UI" / "PauseScreen.cpp"

    if not cheat_cpp.is_file() or not pause_cpp.is_file():
        raise RuntimeError("PPSSPP source tree not found or incomplete")

    helper_anchor = '''static Path GetGlobalCheatFilePath() {
\treturn GetSysDirectory(DIRECTORY_CHEATS) / "cheat.db";
}
'''
    helper_insert = '''static Path GetGlobalCheatFilePath() {
\treturn GetSysDirectory(DIRECTORY_CHEATS) / "cheat.db";
}

// VANTA_CHEAT_ENGINE_R1
// Built-in packs are intentionally disabled by default (_C0).
// They are installed only for an exact DISC_ID match.
struct VantaBuiltinCheatPack {
\tconst char *gameID;
\tconst char *marker;
\tconst char *body;
};

static const VantaBuiltinCheatPack kVantaBuiltinCheatPacks[] = {
\t{
\t\t"ULES00390",
\t\t"VANTA_BUILTIN_ULES00390_R1",
\t\tR"VANTA(
# VANTA_BUILTIN_ULES00390_R1
_S ULES-00390
_G Def Jam: Fight for NY: The Takeover [EU]
_C0 [VANTA] Infinite Cash
_L 0x205ED688 0x3B9AC9FF
_C0 [VANTA] Infinite Dev Points
_L 0x205ED68C 0x3B9AC9FF
)VANTA"
\t},
};

static bool VantaInstallBuiltinCheatPack(const std::string &gameID, const Path &filename) {
\tconst VantaBuiltinCheatPack *pack = nullptr;
\tfor (const auto &candidate : kVantaBuiltinCheatPacks) {
\t\tif (gameID == candidate.gameID) {
\t\t\tpack = &candidate;
\t\t\tbreak;
\t\t}
\t}
\tif (!pack)
\t\treturn false;

\tstd::string existing;
\tFile::ReadTextFileToString(filename, &existing);
\tif (existing.find(pack->marker) != std::string::npos)
\t\treturn false;

\tFILE *out = File::OpenCFile(filename, "at");
\tif (!out)
\t\treturn false;

\tif (!existing.empty() && existing.back() != '\\n')
\t\tfputc('\\n', out);
\tfputs(pack->body, out);
\tfclose(out);
\treturn true;
}
'''
    replace_once(cheat_cpp, helper_anchor, helper_insert, "install VANTA built-in cheat registry")

    create_anchor = '''\t\tengine_ = new CWCheatEngine(gameID_);
\t\tengine_->CreateCheatFile();
\t}
'''
    create_insert = '''\t\tengine_ = new CWCheatEngine(gameID_);
\t\tengine_->CreateCheatFile();
\t\tif (VantaInstallBuiltinCheatPack(gameID_, engine_->CheatFilename())) {
\t\t\tg_Config.bReloadCheats = true;
\t\t}
\t}
'''
    replace_once(cheat_cpp, create_anchor, create_insert, "auto-install matching VANTA cheat pack")

    settings_anchor = '''\tauto mm = GetI18NCategory(I18NCat::MAINMENU);

\t//leftColumn->Add(new Choice(cw->T("Add Cheat")))->OnClick.Handle(this, &CwCheatScreen::OnAddCheat);
'''
    settings_insert = '''\tauto mm = GetI18NCategory(I18NCat::MAINMENU);

\tleftColumn->Add(new ItemHeader("VANTA CHEAT ENGINE"));
\tCheckBox *vantaEngine = leftColumn->Add(new CheckBox(&g_Config.bEnableCheats, "Engine enabled"));
\tvantaEngine->OnClick.Add([](UI::EventParams &) {
\t\tg_Config.bReloadCheats = true;
\t});
\tleftColumn->Add(new Spacer(8.0f));

\t//leftColumn->Add(new Choice(cw->T("Add Cheat")))->OnClick.Handle(this, &CwCheatScreen::OnAddCheat);
'''
    replace_once(cheat_cpp, settings_anchor, settings_insert, "add VANTA engine control")

    title_anchor = '''std::string_view CwCheatScreen::GetTitle() const {
\tauto cw = GetI18NCategory(I18NCat::CWCHEATS);
\treturn cw->T("Cheats");
}
'''
    title_insert = '''std::string_view CwCheatScreen::GetTitle() const {
\treturn "VANTA CHEATS";
}
'''
    replace_once(cheat_cpp, title_anchor, title_insert, "brand cheat screen")

    pause_anchor = '''\tif (g_Config.bEnableCheats && PSP_CoreParameter().fileType != IdentifiedFileType::PPSSPP_GE_DUMP) {
\t\trightColumnItems->Add(new Choice(pa->T("Cheats"), ImageID("I_CHEAT")))->OnClick.Add([this](UI::EventParams &e) {
\t\t\tscreenManager()->push(new CwCheatScreen(gamePath_));
\t\t});
\t}
'''
    pause_insert = '''\t// VANTA_CHEAT_ENGINE_R1: always expose the cheat panel for real games.
\tif (PSP_CoreParameter().fileType != IdentifiedFileType::PPSSPP_GE_DUMP) {
\t\trightColumnItems->Add(new Choice("VANTA CHEATS", ImageID("I_CHEAT")))->OnClick.Add([this](UI::EventParams &e) {
\t\t\tg_Config.bEnableCheats = true;
\t\t\tg_Config.bReloadCheats = true;
\t\t\tscreenManager()->push(new CwCheatScreen(gamePath_));
\t\t});
\t}
'''
    replace_once(pause_cpp, pause_anchor, pause_insert, "expose VANTA cheats in pause menu")

    print("VANTA Cheat Engine R1 applied successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
