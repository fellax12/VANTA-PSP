#!/usr/bin/env python3
"""VANTA PSP R2: patch PPSSPP v1.20.4 AFTER apply_vanta_cheats.py.
GPL-2.0-or-later; see upstream PPSSPP license.
"""
from pathlib import Path
import sys


def replace_exact(path, old, new, description):
    content = path.read_text(encoding="utf-8")
    if new in content:
        print("[skip]", description)
        return
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{description}: expected ONE exact anchor, got {count}: {path}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    print("[ok]", description)


def main():
    if len(sys.argv) != 2:
        print("usage: apply_vanta_scanner_r2.py <PPSSPP-source-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    p = root / "UI/CwCheatScreen.cpp"
    if not p.is_file() or not (root / "Core/MemMap.h").is_file():
        raise RuntimeError("Invalid PPSSPP source root")
    if "VANTA_CHEAT_ENGINE_R1" not in p.read_text(encoding="utf-8"):
        raise RuntimeError("Apply R1 first: missing VANTA_CHEAT_ENGINE_R1")

    replace_exact(p, '#include "UI/MiscViews.h"\n',
'''#include "UI/MiscViews.h"
#include "Core/MemMap.h"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <vector>
''', "scanner includes")

    anchor = 'CwCheatScreen::CwCheatScreen(const Path &gamePath)'
    scanner = r'''// VANTA_MEMORY_SCANNER_R2
// Deliberately scan *emulated PSP user RAM*, never the Android process address space.
// Static session survives closing the pause menu; it is cleared on DISC_ID changes.
namespace {
constexpr u32 VANTA_RAM_START = 0x08800000;
constexpr size_t VANTA_MAX_HITS = 250000;
constexpr size_t VANTA_PAGE_SIZE = 16;

struct VantaScanHit {
    u32 address;
    u32 previous;
};

struct VantaScanSession {
    std::string gameID;
    int width = 4;  // 1, 2, or 4 bytes, unsigned integer.
    bool started = false;
    bool unknown = false;
    bool selected = false;
    u32 selectedAddress = 0;
    u32 selectedValue = 0;
    size_t page = 0;
    std::vector<VantaScanHit> hits;
    std::vector<u8> baseline;  // Only used for unknown-first-scan, at most PSP user RAM size.
    std::string message = "Start with Exact or Unknown, then resume the game to change a value.";
};
VantaScanSession vantaScan;

u32 VantaRamLength() {
    // The 0x08000000-0x08800000 kernel/volatile area isn't representable
    // using a normal CWCheat base-relative address, so don't scan it.
    return Memory::g_MemorySize > 0x00800000 ? Memory::g_MemorySize - 0x00800000 : 0;
}

u32 VantaMask() {
    return vantaScan.width == 1 ? 0xFFu : vantaScan.width == 2 ? 0xFFFFu : 0xFFFFFFFFu;
}

bool VantaParse(const std::string &text, u32 *value) {
    if (text.empty() || text[0] == '-' || text[0] == '+') return false;
    errno = 0;
    char *end = nullptr;
    // Decimal by default. A leading 0x opts into hexadecimal.
    const int base = text.size() > 2 && text[0] == '0' && (text[1] == 'x' || text[1] == 'X') ? 16 : 10;
    const unsigned long long n = std::strtoull(text.c_str(), &end, base);
    if (errno || end == text.c_str() || *end != '\0' || n > VantaMask()) return false;
    *value = (u32)n;
    return true;
}

u32 VantaReadBytes(const u8 *p) {
    if (vantaScan.width == 1) return p[0];
    if (vantaScan.width == 2) return (u32)p[0] | ((u32)p[1] << 8);
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

u32 VantaRead(u32 address) {
    if (vantaScan.width == 1) return Memory::ReadUnchecked_U8(address);
    if (vantaScan.width == 2) return Memory::ReadUnchecked_U16(address);
    return Memory::ReadUnchecked_U32(address);
}

void VantaReset(const std::string &gameID) {
    vantaScan = VantaScanSession{};
    vantaScan.gameID = gameID;
}

const u8 *VantaGetRAM(u32 *length) {
    *length = VantaRamLength();
    if (!Memory::base || *length < 4 || !Memory::IsValidRange(VANTA_RAM_START, *length)) return nullptr;
    return Memory::GetPointerRange(VANTA_RAM_START, *length);
}

void VantaBeginExact(u32 requested) {
    u32 len = 0;
    const u8 *ram = VantaGetRAM(&len);
    if (!ram) {
        vantaScan.message = "PSP RAM unavailable. Start a real game first.";
        return;
    }
    vantaScan.hits.clear();
    vantaScan.baseline.clear();
    vantaScan.started = false;
    vantaScan.unknown = false;
    vantaScan.selected = false;
    vantaScan.page = 0;
    vantaScan.hits.reserve(4096);
    const u32 width = (u32)vantaScan.width;
    for (u32 offset = 0; offset <= len - width; offset += width) {
        const u32 n = VantaReadBytes(ram + offset);
        if (n == requested) {
            if (vantaScan.hits.size() == VANTA_MAX_HITS) {
                vantaScan.hits.clear();
                vantaScan.message = "Too many hits (>250000). Use a less common value or 32-bit width.";
                return;  // Never present a truncated set as a complete search.
            }
            vantaScan.hits.push_back({VANTA_RAM_START + offset, n});
        }
    }
    vantaScan.started = true;
    vantaScan.message = StringFromFormat("Exact first scan: %u matches (%d-bit)",
        (unsigned)vantaScan.hits.size(), vantaScan.width * 8);
}

void VantaBeginUnknown() {
    u32 len = 0;
    const u8 *ram = VantaGetRAM(&len);
    if (!ram) {
        vantaScan.message = "PSP RAM unavailable. Start a real game first.";
        return;
    }
    vantaScan.hits.clear();
    vantaScan.baseline.assign(ram, ram + len);
    vantaScan.started = true;
    vantaScan.unknown = true;
    vantaScan.selected = false;
    vantaScan.page = 0;
    vantaScan.message = "Unknown baseline saved. Resume game, change number, then Next Scan.";
}

enum VantaCompare { VANTA_EXACT, VANTA_CHANGED, VANTA_UNCHANGED, VANTA_INCREASED, VANTA_DECREASED };
bool VantaMatches(u32 current, u32 prior, VantaCompare mode, u32 exact) {
    switch (mode) {
    case VANTA_EXACT: return current == exact;
    case VANTA_CHANGED: return current != prior;
    case VANTA_UNCHANGED: return current == prior;
    case VANTA_INCREASED: return current > prior;
    case VANTA_DECREASED: return current < prior;
    }
    return false;
}

void VantaNextScan(VantaCompare mode, u32 exact = 0) {
    if (!vantaScan.started) {
        vantaScan.message = "Start a first scan before refining.";
        return;
    }
    u32 len = 0;
    const u8 *ram = VantaGetRAM(&len);
    if (!ram) {
        vantaScan.message = "PSP RAM unavailable.";
        return;
    }
    const u32 width = (u32)vantaScan.width;
    std::vector<VantaScanHit> next;
    next.reserve(vantaScan.unknown ? 4096 : vantaScan.hits.size());
    if (vantaScan.unknown) {
        if (vantaScan.baseline.size() != len) {
            vantaScan.message = "PSP RAM size changed; start a new scan.";
            return;
        }
        for (u32 off = 0; off <= len - width; off += width) {
            const u32 before = VantaReadBytes(vantaScan.baseline.data() + off);
            const u32 after = VantaReadBytes(ram + off);
            if (VantaMatches(after, before, mode, exact)) {
                if (next.size() == VANTA_MAX_HITS) {
                    vantaScan.message = "Too many results (>250000). Try Decreased, Increased, or Exact.";
                    return;  // Keep baseline to retry a narrower comparison.
                }
                next.push_back({VANTA_RAM_START + off, after});
            }
        }
    } else {
        for (const auto &hit : vantaScan.hits) {
            if (!Memory::IsValidRange(hit.address, width)) continue;
            const u32 after = VantaRead(hit.address);
            if (VantaMatches(after, hit.previous, mode, exact)) {
                next.push_back({hit.address, after});
            }
        }
    }
    vantaScan.hits.swap(next);
    vantaScan.baseline.clear();
    vantaScan.baseline.shrink_to_fit();
    vantaScan.unknown = false;
    vantaScan.selected = false;
    vantaScan.page = 0;
    vantaScan.message = StringFromFormat("Next scan: %u candidates. Select an address on the right.",
        (unsigned)vantaScan.hits.size());
}

bool VantaWrite(u32 address, u32 value) {
    if (address < VANTA_RAM_START ||
        !Memory::IsValidRange(address, (u32)vantaScan.width) ||
        (address & (vantaScan.width - 1)) != 0 || value > VantaMask()) return false;
    if (vantaScan.width == 1) Memory::Write_U8((u8)value, address);
    else if (vantaScan.width == 2) Memory::Write_U16((u16)value, address);
    else Memory::Write_U32(value, address);
    for (auto &hit : vantaScan.hits) {
        if (hit.address == address) hit.previous = value;
    }
    vantaScan.selectedValue = value;
    return true;
}
}  // anonymous namespace / VANTA_MEMORY_SCANNER_R2

'''
    replace_exact(p, anchor, scanner + anchor, "inject native PSP RAM scanner")

    replace_exact(p, 'static bool VantaInstallBuiltinCheatPack(',
        '[[maybe_unused]] static bool VantaInstallBuiltinCheatPack(',
        "retain unused R1 helper without compiler warning")

    # Do not seed the two unverified R1 addresses into new game cheat files.
    replace_exact(p,
'''		if (VantaInstallBuiltinCheatPack(gameID_, engine_->CheatFilename())) {
			g_Config.bReloadCheats = true;
		}
''',
'''		// VANTA R2: stop automatically importing unverified R1 addresses.
		// Pre-existing _C0 entries remain user-manageable in the cheat list.
''', "disable unverified R1 auto-import")
    replace_exact(p,
'''	gameID = info->GetParamSFO().GetValueString("DISC_ID");
''',
'''	gameID = info->GetParamSFO().GetValueString("DISC_ID");
''', "no-op never executed") if False else None
    replace_exact(p,
'''	if (!engine_ || gameID != gameID_) {
		gameID_ = gameID;
''',
'''	if (!engine_ || gameID != gameID_) {
		if (vantaScan.gameID != gameID) VantaReset(gameID);
		gameID_ = gameID;
''', "reset scanner on DISC_ID change")

    replace_exact(p,
        'Choice *searchChoice = leftColumn->Add(new Choice(di->T("Search"), ImageID("I_SEARCH")));',
        'Choice *searchChoice = leftColumn->Add(new Choice("Filter cheat names (not RAM)", ImageID("I_SEARCH")));',
        "disambiguate original cheat-name filter")

    settings_anchor = '''	leftColumn->Add(new ItemHeader(cw->T("Import Cheats")));'''
    settings_insert = r'''	// VANTA R2 native scanner settings. The old "Search" below still filters cheat *names*.
    leftColumn->Add(new ItemHeader("VANTA MEMORY SCANNER R2"));
    leftColumn->Add(new Choice(StringFromFormat("Data width: %d-bit (tap to cycle)", vantaScan.width * 8)))->OnClick.Add([this](UI::EventParams &) {
        const int next = vantaScan.width == 1 ? 2 : vantaScan.width == 2 ? 4 : 1;
        const std::string id = vantaScan.gameID;
        VantaReset(id);
        vantaScan.width = next;
        RecreateViews();
    });
    Choice *vantaFirst = leftColumn->Add(new Choice("First Scan: Exact value"));
    vantaFirst->OnClick.Add([this, vantaFirst](UI::EventParams &) {
        AskForInput(screenManager(), GetRequesterToken(), vantaFirst, "Exact value: decimal or 0xHEX", [this](const std::string &input, bool ok) {
            if (!ok) return;
            u32 value = 0;
            if (!VantaParse(input, &value)) vantaScan.message = "Invalid value for selected 8/16/32-bit width.";
            else VantaBeginExact(value);
            RecreateViews();
        });
    });
    leftColumn->Add(new Choice("First Scan: Unknown value"))->OnClick.Add([this](UI::EventParams &) {
        VantaBeginUnknown();
        RecreateViews();
    });
    Choice *vantaExact = leftColumn->Add(new Choice("Next Scan: Exact value"));
    vantaExact->OnClick.Add([this, vantaExact](UI::EventParams &) {
        AskForInput(screenManager(), GetRequesterToken(), vantaExact, "New exact value", [this](const std::string &input, bool ok) {
            if (!ok) return;
            u32 value = 0;
            if (!VantaParse(input, &value)) vantaScan.message = "Invalid value for selected width.";
            else VantaNextScan(VANTA_EXACT, value);
            RecreateViews();
        });
    });
    leftColumn->Add(new Choice("Next Scan: Decreased"))->OnClick.Add([this](UI::EventParams &) {
        VantaNextScan(VANTA_DECREASED); RecreateViews();
    });
    leftColumn->Add(new Choice("Next Scan: Increased"))->OnClick.Add([this](UI::EventParams &) {
        VantaNextScan(VANTA_INCREASED); RecreateViews();
    });
    leftColumn->Add(new Choice("Next Scan: Changed"))->OnClick.Add([this](UI::EventParams &) {
        VantaNextScan(VANTA_CHANGED); RecreateViews();
    });
    leftColumn->Add(new Choice("Next Scan: Unchanged"))->OnClick.Add([this](UI::EventParams &) {
        VantaNextScan(VANTA_UNCHANGED); RecreateViews();
    });
    leftColumn->Add(new Choice("Clear scan"))->OnClick.Add([this](UI::EventParams &) {
        const int width = vantaScan.width;
        const std::string id = vantaScan.gameID;
        VantaReset(id);
        vantaScan.width = width;
        RecreateViews();
    });
    if (vantaScan.selected) {
        leftColumn->Add(new ItemHeader(StringFromFormat("SELECTED 0x%08X", vantaScan.selectedAddress)));
        Choice *vantaEdit = leftColumn->Add(new Choice("Write new value (once)"));
        vantaEdit->OnClick.Add([this, vantaEdit](UI::EventParams &) {
            const u32 address = vantaScan.selectedAddress;
            AskForInput(screenManager(), GetRequesterToken(), vantaEdit, "Write value (decimal or 0xHEX)", [this, address](const std::string &input, bool ok) {
                if (!ok) return;
                u32 value = 0;
                if (!VantaParse(input, &value) || !VantaWrite(address, value)) {
                    vantaScan.message = "Write failed: invalid value or unmapped address.";
                } else {
                    vantaScan.message = StringFromFormat("Wrote %u at 0x%08X. Resume game to verify.", value, address);
                }
                RecreateViews();
            });
        });
        leftColumn->Add(new Choice("Save selected value as ENABLED CWCheat"))->OnClick.Add([this](UI::EventParams &) {
            if (!engine_ || gameID_.empty() || !vantaScan.selected) return;
            const u32 address = vantaScan.selectedAddress;
            const u32 width = (u32)vantaScan.width;
            const u32 value = vantaScan.selectedValue;
            if (address < VANTA_RAM_START || !Memory::IsValidRange(address, width) || value > VantaMask()) {
                vantaScan.message = "Cannot export selected address/width.";
                RecreateViews();
                return;
            }
            const u32 relative = address - VANTA_RAM_START;
            const u32 code = (width == 1 ? 0x00000000u : width == 2 ? 0x10000000u : 0x20000000u) | relative;
            const std::string marker = StringFromFormat("# VANTA_R2_%08X_%u", address, width);
            std::string existing;
            File::ReadTextFileToString(engine_->CheatFilename(), &existing);
            if (existing.find(marker) != std::string::npos) {
                vantaScan.message = "This address/width is already saved. Disable/edit its prior entry first.";
                RecreateViews();
                return;
            }
            FILE *f = File::OpenCFile(engine_->CheatFilename(), "at");
            if (!f) {
                vantaScan.message = "Could not open the game's CWCheat file.";
                RecreateViews();
                return;
            }
            if (!existing.empty() && existing.back() != '\n') fputc('\n', f);
            fprintf(f, "%s\n_C1 [VANTA R2] %08X = %u\n_L 0x%08X 0x%08X\n", marker.c_str(), address, value, code, value);
            fclose(f);
            g_Config.bEnableCheats = true;
            g_Config.bReloadCheats = true;
            vantaScan.message = "Saved and enabled CWCheat. Resume game to confirm it is stable.";
            RecreateViews();
        });
    }
    leftColumn->Add(new Spacer(8.0f));

'''.replace(r'\t','\t')
    # Above is a raw literal containing a literal backslash-t in the first line only.
    settings_insert = settings_insert.replace('\\t// VANTA R2', '\t// VANTA R2')
    replace_exact(p, settings_anchor, settings_insert + settings_anchor, "add R2 controls")

    results_anchor = '''	rightColumn->Add(new ItemHeader(cw->T("Cheats")));'''
    results_insert = r'''	// VANTA MEMORY SCANNER R2: result cards are *not* the name-filter SearchBar above.
    rightColumn->Add(new ItemHeader("VANTA RAM SCAN RESULTS"));
    rightColumn->Add(new TextView(vantaScan.message, new LinearLayoutParams(FILL_PARENT, WRAP_CONTENT, UI::Margins(8, 8, 8, 8))));
    if (vantaScan.started && !vantaScan.unknown) {
        rightColumn->Add(new TextView(StringFromFormat("Found: %u | width: %d-bit", (unsigned)vantaScan.hits.size(), vantaScan.width * 8),
            new LinearLayoutParams(FILL_PARENT, WRAP_CONTENT, UI::Margins(8, 8, 8, 8))));
        const size_t begin = vantaScan.page * VANTA_PAGE_SIZE;
        const size_t end = std::min(begin + VANTA_PAGE_SIZE, vantaScan.hits.size());
        for (size_t index = begin; index < end; ++index) {
            const u32 address = vantaScan.hits[index].address;
            const u32 current = Memory::IsValidRange(address, (u32)vantaScan.width) ? VantaRead(address) : 0;
            const bool picked = vantaScan.selected && vantaScan.selectedAddress == address;
            Choice *row = rightColumn->Add(new Choice(StringFromFormat("%s0x%08X : %u (0x%X)",
                picked ? "> " : "", address, current, current)));
            row->OnClick.Add([this, address](UI::EventParams &) {
                if (!Memory::IsValidRange(address, (u32)vantaScan.width)) return;
                vantaScan.selected = true;
                vantaScan.selectedAddress = address;
                vantaScan.selectedValue = VantaRead(address);
                vantaScan.message = "Address selected. Use Write or Save on the left.";
                RecreateViews();
            });
        }
        if (begin > 0) {
            rightColumn->Add(new Choice("Previous results page"))->OnClick.Add([this](UI::EventParams &) {
                if (vantaScan.page > 0) --vantaScan.page;
                RecreateViews();
            });
        }
        if (end < vantaScan.hits.size()) {
            rightColumn->Add(new Choice("Next results page"))->OnClick.Add([this](UI::EventParams &) {
                ++vantaScan.page;
                RecreateViews();
            });
        }
    }
    rightColumn->Add(new Spacer(8.0f));

'''
    results_insert = results_insert.replace('\\t// VANTA MEMORY', '\t// VANTA MEMORY')
    replace_exact(p, results_anchor, results_insert + results_anchor, "show paginated native scan results")
    print("[ok] VANTA Memory Scanner R2 patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
