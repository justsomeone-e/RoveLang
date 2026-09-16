# -*- coding: utf-8 -*-
"""
Tour of Nyx - Interactive Guided Learning CLI
Inspired by Rustlings, engineered for the Nyx programming language with
a modern terminal user interface, instant diagnostics, and live file watching.
"""

import os
import sys
import json
import time
import argparse
from typing import Optional, Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ui import (
    render_banner,
    render_progress,
    format_error_card,
    format_success_card,
    format_info_card,
    format_hint_card,
    format_controls,
    box,
    clear_screen,
    BOLD,
    DIM,
    RESET,
    WHITE,
    COLOR_NYX_PURPLE,
    COLOR_NYX_VIOLET,
    COLOR_NYX_CYAN,
    COLOR_NYX_GREEN,
    COLOR_NYX_GOLD,
    COLOR_NYX_RED,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_YELLOW,
    BRIGHT_WHITE,
)
from runner import NyxRunner, TestResult


STATE_FILE = ".tour-state.json"


class TourApp:
    def __init__(self, tour_dir: Optional[str] = None, workspace_dir: Optional[str] = None,
                 track: str = "all"):
        self.tour_dir = tour_dir or os.path.dirname(os.path.abspath(__file__))
        self.workspace_dir = os.path.abspath(workspace_dir) if workspace_dir else self.tour_dir
        self.repo_dir = os.path.abspath(os.path.join(self.tour_dir, ".."))
        self.track = track
        self.exercises_file = os.path.join(self.workspace_dir, "exercises.json")
        if not os.path.isfile(self.exercises_file):
            self.exercises_file = os.path.join(self.tour_dir, "exercises.json")
        state_file = STATE_FILE if track == "all" else f".tour-{track}-state.json"
        self.state_path = os.path.join(self.workspace_dir, state_file)

        self.exercises: List[Dict[str, Any]] = self._load_exercises()
        self.lessons = self._load_lessons()
        self.runner = NyxRunner(repo_dir=self.repo_dir)

        self.state = self._load_state()
        self.current_index = self._determine_starting_index()
        self.hint_levels: Dict[str, int] = self.state.get("hints_shown", {})
        self.show_solution = False
        self.active_hint: Optional[str] = None

    def _load_exercises(self) -> List[Dict[str, Any]]:
        if not os.path.isfile(self.exercises_file):
            print(f"Error: {self.exercises_file} not found.")
            sys.exit(1)
        with open(self.exercises_file, "r", encoding="utf-8") as f:
            exercises = json.load(f)
        if self.track == "all":
            return exercises

        track_file = os.path.join(self.tour_dir, f"{self.track}_path.json")
        if not os.path.isfile(track_file):
            raise ValueError(f"Unknown Tour track: {self.track}")
        with open(track_file, "r", encoding="utf-8") as f:
            track_ids = json.load(f)
        by_id = {exercise["id"]: exercise for exercise in exercises}
        missing = [exercise_id for exercise_id in track_ids if exercise_id not in by_id]
        if missing:
            raise ValueError(f"Tour track contains unknown exercise IDs: {', '.join(missing)}")
        return [by_id[exercise_id] for exercise_id in track_ids]

    def _load_lessons(self) -> Dict[str, Dict[str, str]]:
        if self.track != "core":
            return {}
        lesson_file = os.path.join(self.tour_dir, "core_lessons.json")
        if not os.path.isfile(lesson_file):
            return {}
        with open(lesson_file, "r", encoding="utf-8") as f:
            lessons = json.load(f)
        missing = [exercise["id"] for exercise in self.exercises if exercise["id"] not in lessons]
        if missing:
            raise ValueError(f"Core lessons missing exercise IDs: {', '.join(missing)}")
        return lessons

    def _load_state(self) -> Dict[str, Any]:
        if os.path.isfile(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"completed": [], "current_index": 0, "hints_shown": {}}

    def _save_state(self):
        self.state["current_index"] = self.current_index
        self.state["hints_shown"] = self.hint_levels
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _determine_starting_index(self) -> int:
        completed = set(self.state.get("completed", []))
        for i, ex in enumerate(self.exercises):
            if ex["id"] not in completed:
                return i
        return max(0, len(self.exercises) - 1)

    def get_current_exercise(self) -> Dict[str, Any]:
        return self.exercises[self.current_index]

    def mark_completed(self, exercise_id: str):
        completed = set(self.state.get("completed", []))
        if exercise_id not in completed:
            completed.add(exercise_id)
            self.state["completed"] = sorted(list(completed))
            self._save_state()

    def get_exercise_file_path(self, ex: Dict[str, Any]) -> str:
        return os.path.join(self.workspace_dir, ex["path"])

    def get_solution_file_path(self, ex: Dict[str, Any]) -> str:
        return os.path.join(self.tour_dir, ex["solution"])

    def open_current_in_editor(self):
        """Open the active exercise in VS Code or system default editor."""
        import shutil
        import subprocess
        ex = self.get_current_exercise()
        fpath = self.get_exercise_file_path(ex)
        code_bin = shutil.which("code")
        try:
            if code_bin:
                subprocess.Popen([code_bin, fpath], shell=False)
            elif sys.platform == "win32":
                os.startfile(fpath)
            else:
                subprocess.Popen(["xdg-open", fpath])
        except Exception:
            pass

    def open_exercises_folder(self):
        """Open the exercises folder in Windows Explorer or file manager."""
        import subprocess
        folder = os.path.join(self.workspace_dir, "exercises")
        if not os.path.isdir(folder):
            folder = os.path.join(self.tour_dir, "exercises")
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    def render_view(self, last_result: TestResult):
        clear_screen()
        ex = self.get_current_exercise()
        completed_count = len(self.state.get("completed", []))
        total_count = len(self.exercises)

        # 1. Header Banner
        print(render_banner())
        print()

        # 2. Progress Meter
        prog = render_progress(completed_count, total_count)
        print(f"  {prog}")
        print()

        # 3. Lesson Info Card
        ex_path = ex["path"]
        hint_lvl = self.hint_levels.get(ex["id"], 0)
        print(format_info_card(
            ex["topic"], ex_path, ex["description"], hint_lvl,
            self.lessons.get(ex["id"])
        ))
        print()

        # 4. Result Card (Success or Error)
        if last_result.success:
            self.mark_completed(ex["id"])
            print(format_success_card(ex["title"], ex_path, last_result.output))
        else:
            print(format_error_card(ex_path, last_result.error))
        print()

        # 5. Hint Card (if active)
        if self.active_hint:
            hints = ex.get("hints", [])
            print(format_hint_card(self.active_hint, hint_lvl, len(hints)))
            print()

        # 6. Solution Card (if requested)
        if self.show_solution:
            sol_path = self.get_solution_file_path(ex)
            if os.path.isfile(sol_path):
                with open(sol_path, "r", encoding="utf-8") as sf:
                    sol_code = sf.read().strip()
                print(box("Reference Solution", sol_code, color_seq=COLOR_NYX_GOLD))
                print()

        # 7. Navigation Controls
        print(format_controls())
        print()

    def check_key(self) -> Optional[str]:
        """Non-blocking keyboard reader."""
        if sys.platform == "win32":
            import msvcrt
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"\x00", b"\xe0"):
                    # Extended key
                    msvcrt.getch()
                    return None
                try:
                    return ch.decode("utf-8").lower()
                except Exception:
                    return None
            return None
        else:
            import select
            dr, _, _ = select.select([sys.stdin], [], [], 0)
            if dr:
                return sys.stdin.read(1).lower()
            return None

    def show_hint(self):
        ex = self.get_current_exercise()
        hints = ex.get("hints", [])
        if not hints:
            self.active_hint = "No hints available for this exercise."
            return

        curr_lvl = self.hint_levels.get(ex["id"], 0)
        next_lvl = (curr_lvl % len(hints)) + 1
        self.hint_levels[ex["id"]] = next_lvl
        self.active_hint = hints[next_lvl - 1]
        self._save_state()

    def show_curriculum_list(self):
        clear_screen()
        completed = set(self.state.get("completed", []))
        total = len(self.exercises)
        done = len(completed)

        print(render_banner())
        print()
        print(f"  {BOLD}Curriculum Overview:{RESET}  {done}/{total} Completed")
        print()

        # Group by topic
        topics: Dict[str, List[Dict[str, Any]]] = {}
        for ex in self.exercises:
            t = ex["topic"]
            if t not in topics:
                topics[t] = []
            topics[t].append(ex)

        for topic, ex_list in topics.items():
            print(f"  {BOLD}{COLOR_NYX_VIOLET}▶ {topic.upper()}{RESET}")
            for ex in ex_list:
                eid = ex["id"]
                is_curr = (eid == self.get_current_exercise()["id"])
                is_done = eid in completed

                if is_curr:
                    pointer = f"{BOLD}{BRIGHT_CYAN}➜{RESET}"
                else:
                    pointer = " "

                if is_done:
                    badge = f"{BOLD}{COLOR_NYX_GREEN}✔{RESET}"
                else:
                    badge = f"{DIM}○{RESET}"

                name_fmt = f"{eid:<14}"
                if is_curr:
                    name_fmt = f"{BOLD}{BRIGHT_CYAN}{name_fmt}{RESET}"
                elif is_done:
                    name_fmt = f"{COLOR_NYX_GREEN}{name_fmt}{RESET}"
                else:
                    name_fmt = f"{WHITE}{name_fmt}{RESET}"

                print(f"    {pointer} {badge} {name_fmt} {DIM}― {ex['title']}{RESET}")
            print()

        print(f"  {DIM}Press any key to return to current exercise...{RESET}")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.getch()
        else:
            sys.stdin.read(1)

    def run_single(self, exercise_name: str):
        target = None
        for ex in self.exercises:
            if ex["id"] == exercise_name or ex["name"] == exercise_name:
                target = ex
                break

        if not target:
            print(f"Exercise '{exercise_name}' not found.")
            return

        res = self.runner.verify(target)
        if res.success:
            print(f"✅ {target['id']}: Success!")
            if res.output:
                print(res.output)
        else:
            print(f"❌ {target['id']}: Failed.")
            print(res.error)

    def check_all(self):
        print(render_banner())
        print()
        print(f"{BOLD}Verifying all {len(self.exercises)} exercises against compiler...{RESET}")
        print()

        done_count = 0
        for idx, ex in enumerate(self.exercises, 1):
            res = self.runner.verify(ex)
            if res.success:
                status = f"{BOLD}{COLOR_NYX_GREEN}✔ DONE{RESET}"
                done_count += 1
                self.mark_completed(ex["id"])
            else:
                status = f"{BOLD}{COLOR_NYX_RED}✗ PENDING{RESET}"

            print(f"  [{idx:02d}/{len(self.exercises)}] {status}  {ex['id']:<14} {DIM}{ex['title']}{RESET}")

        print()
        pct = (done_count / len(self.exercises)) * 100
        print(f"{BOLD}Overall Status: {done_count}/{len(self.exercises)} solved ({pct:.1f}%){RESET}")

    def watch(self):
        """Main watch mode event loop."""
        ex = self.get_current_exercise()
        file_path = self.get_exercise_file_path(ex)
        last_mtime = os.path.getmtime(file_path) if os.path.isfile(file_path) else 0

        # Initial test
        res = self.runner.verify(ex)
        self.render_view(res)

        while True:
            time.sleep(0.15)

            # Check file modification
            if os.path.isfile(file_path):
                current_mtime = os.path.getmtime(file_path)
                if current_mtime != last_mtime:
                    last_mtime = current_mtime
                    self.show_solution = False
                    res = self.runner.verify(ex)
                    self.render_view(res)

            # Check keyboard commands
            k = self.check_key()
            if not k:
                continue

            if k == "q":
                clear_screen()
                print(f"\n{BOLD}{COLOR_NYX_VIOLET}Tour of Nyx saved! See you soon. 🌙{RESET}\n")
                self._save_state()
                break

            elif k == "n":
                if self.current_index < len(self.exercises) - 1:
                    self.current_index += 1
                    self.active_hint = None
                    self.show_solution = False
                    self._save_state()
                    ex = self.get_current_exercise()
                    file_path = self.get_exercise_file_path(ex)
                    last_mtime = os.path.getmtime(file_path) if os.path.isfile(file_path) else 0
                    res = self.runner.verify(ex)
                    self.render_view(res)
                else:
                    self.render_view(res)

            elif k == "p":
                if self.current_index > 0:
                    self.current_index -= 1
                    self.active_hint = None
                    self.show_solution = False
                    self._save_state()
                    ex = self.get_current_exercise()
                    file_path = self.get_exercise_file_path(ex)
                    last_mtime = os.path.getmtime(file_path) if os.path.isfile(file_path) else 0
                    res = self.runner.verify(ex)
                    self.render_view(res)

            elif k == "h":
                self.show_hint()
                self.render_view(res)

            elif k == "r":
                res = self.runner.verify(ex)
                self.render_view(res)

            elif k == "s":
                self.show_solution = not self.show_solution
                self.render_view(res)

            elif k == "o":
                self.open_current_in_editor()

            elif k == "e":
                self.open_exercises_folder()

            elif k == "l":
                self.show_curriculum_list()
                self.render_view(res)


    def reset_exercise(self, exercise_name: Optional[str] = None):
        import build_curriculum
        if exercise_name is None or exercise_name.lower() == "all":
            build_curriculum.build()
            self.state = {"completed": [], "current_index": 0, "hints_shown": {}}
            self._save_state()
            print("🔄 Reset all exercises and learner progress to initial state!")
        else:
            found = False
            for ex_data in build_curriculum.EXERCISES_DATA:
                if ex_data["id"] == exercise_name or ex_data["name"] == exercise_name:
                    ex_path = os.path.join(self.tour_dir, ex_data["path"])
                    with open(ex_path, "w", encoding="utf-8") as f:
                        f.write(ex_data["exercise_code"])
                    completed = set(self.state.get("completed", []))
                    completed.discard(ex_data["id"])
                    self.state["completed"] = sorted(list(completed))
                    self._save_state()
                    print(f"🔄 Reset exercise '{ex_data['id']}' to initial state.")
                    found = True
                    break
            if not found:
                print(f"❌ Exercise '{exercise_name}' not found.")


def init_workspace(target_path: Optional[str] = None):
    """Scaffold a standalone learner exercises directory anywhere on disk."""
    import shutil
    base_tour_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.abspath(os.path.join(base_tour_dir, ".."))

    if not target_path:
        target_path = os.path.join(os.path.expanduser("~"), "Desktop", "Nyx_Tour_Exercises")

    target_path = os.path.abspath(target_path)
    os.makedirs(target_path, exist_ok=True)

    # 1. Copy only exercises referenced by the canonical manifest. This avoids
    # leaking renamed or retired lessons into a learner workspace.
    src_exercises = os.path.join(base_tour_dir, "exercises")
    dest_exercises = os.path.join(target_path, "exercises")
    if os.path.exists(dest_exercises):
        shutil.rmtree(dest_exercises)
    with open(os.path.join(base_tour_dir, "exercises.json"), "r", encoding="utf-8") as manifest_file:
        curriculum = json.load(manifest_file)
    for exercise in curriculum:
        relative_path = os.path.relpath(exercise["path"], "exercises")
        source_path = os.path.join(src_exercises, relative_path)
        destination_path = os.path.join(dest_exercises, relative_path)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copyfile(source_path, destination_path)

    # 2. Copy exercises.json
    shutil.copyfile(
        os.path.join(base_tour_dir, "exercises.json"),
        os.path.join(target_path, "exercises.json")
    )

    # 3. Create start_tour.bat in target_path
    tour_bat_in_repo = os.path.join(repo_dir, "tour.bat")
    start_bat_content = f"""@echo off
setlocal
chcp 65001 >nul 2>&1
title Tour of Nyx
call "{tour_bat_in_repo}" --workspace "{target_path}" %*
pause
"""
    with open(os.path.join(target_path, "start_tour.bat"), "w", encoding="utf-8") as f:
        f.write(start_bat_content)

    # 4. Create BENI_OKU.txt in target_path
    readme_content = f"""Tour of Nyx - Alıştırma Klasörü 🌙
======================================================================
Bu klasör, Nyx programlama dilini öğrenmeniz için bilerek hatalı veya
eksik bırakılmış {len(curriculum)} alıştırmayı içerir.

Nasıl Çalışır?
1. Bu klasörü VS Code veya favori metin düzenleyicinizde açın:
   Klasöre sağ tıklayın -> "Open with Code" (veya terminalde: code .)
2. "start_tour.bat" dosyasını çift tıklayarak çalıştırın.
3. Terminalde sıradaki dersin konusu, ipuçları ve hata mesajı belirir.
4. VS Code'da ilgili .nyx dosyasını açıp kodunu düzeltin ve kaydedin (Ctrl + S).
5. Terminal kaydettiğinizi ANINDA algılar, doğrular ve çözüldüğünde bir sonrakine geçer!
======================================================================
"""
    with open(os.path.join(target_path, "BENI_OKU.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)

    print("=" * 70)
    print("✨ Nyx Tour Öğrenci Çalışma Alanı Başarıyla Oluşturuldu!")
    print(f"📁 Konum: {target_path}")
    print("=" * 70)
    print("1. Klasördeki 'start_tour.bat' dosyasını çalıştırarak turu başlatın.")
    print("2. 'exercises/' klasöründeki dosyaları VS Code'da düzenleyip kaydedin.")
    print("3. Sistem dosya kaydetmelerinizi (Ctrl+S) canlı olarak takip eder!")
    print("=" * 70)

    # Open VS Code & Explorer
    code_bin = shutil.which("code")
    if code_bin:
        try:
            import subprocess
            subprocess.Popen([code_bin, target_path], shell=False)
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            os.startfile(target_path)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Tour of Nyx - Interactive Terminal Learning CLI")
    parser.add_argument("command", nargs="?", default="watch",
                        choices=["watch", "core", "run", "check-all", "hint", "list", "reset", "init"],
                        help="Tour command (default: watch)")
    parser.add_argument("exercise", nargs="?", default=None, help="Target exercise name, id, or init path")
    parser.add_argument("--workspace", default=None, help="Path to student exercise workspace directory")
    parser.add_argument("--track", choices=["all", "core"], default="all",
                        help="Exercise track to use (default: all)")

    args = parser.parse_args()

    if args.command == "init":
        init_workspace(args.exercise)
        return

    track = "core" if args.command == "core" else args.track
    app = TourApp(workspace_dir=args.workspace, track=track)

    if args.command in ("watch", "core"):
        app.watch()
    elif args.command == "run":
        if args.exercise:
            app.run_single(args.exercise)
        else:
            app.run_single(app.get_current_exercise()["id"])
    elif args.command == "check-all":
        app.check_all()
    elif args.command == "hint":
        app.show_hint()
        if app.active_hint:
            print(f"\n💡 Hint: {app.active_hint}\n")
    elif args.command == "list":
        app.show_curriculum_list()
    elif args.command == "reset":
        app.reset_exercise(args.exercise)


if __name__ == "__main__":
    main()
