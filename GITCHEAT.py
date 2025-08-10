#!/usr/bin/env python3
"""
Senior DevOps Git Helper (safe delete branch included + push staging->main)

- Uses only Python stdlib + Git CLI
- Interactive, cautious workflow
- Local & remote branch delete with many safeguards
- Push staging -> main with strong safeguards & optional backup
- Keeps audit log at <repo-root>/.git/git_helper_actions.log
"""

import subprocess
import os
import sys
from datetime import datetime
import shutil

# ---------------- Utility ----------------
PROTECTED_BRANCHES = {"main", "master", "develop", "production", "prod", "staging", "release"}
LOG_FILENAME = ".git/git_helper_actions.log"

def git_available():
    return shutil.which("git") is not None

def run_git(args, capture=True):
    """Run a git command (args is list) and return CompletedProcess."""
    return subprocess.run(["git"] + args, capture_output=capture, text=True)

def print_run_git(args):
    cp = run_git(args)
    if cp.stdout:
        print(cp.stdout.strip())
    if cp.returncode != 0 and cp.stderr:
        print(f"❌ git {' '.join(args)} error: {cp.stderr.strip()}")
    return cp

def confirm(prompt):
    r = input(f"{prompt} (y/n): ").strip().lower()
    return r == "y"

def typed_confirm(prompt, expected):
    """Ask the user to type an exact expected string to confirm."""
    print(prompt)
    typed = input("Type the exact text to confirm: ").strip()
    return typed == expected

def get_repo_root():
    cp = run_git(["rev-parse", "--show-toplevel"])
    if cp.returncode != 0:
        return None
    return cp.stdout.strip()

def log_action(repo_root, msg):
    if not repo_root:
        return
    log_path = os.path.join(repo_root, LOG_FILENAME)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def get_current_branch():
    cp = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if cp.returncode != 0:
        return None
    return cp.stdout.strip()

def list_local_branches():
    cp = run_git(["branch", "--format=%(refname:short)"])
    if cp.returncode != 0:
        return []
    return [b.strip() for b in cp.stdout.splitlines() if b.strip()]

def list_remote_branches(remote="origin"):
    cp = run_git(["ls-remote", "--heads", remote])
    if cp.returncode != 0:
        return []
    names = []
    for line in cp.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            ref = parts[1]
            if ref.startswith("refs/heads/"):
                names.append(ref[len("refs/heads/"):])
    return names

def branch_exists_local(branch):
    return branch in list_local_branches()

def branch_exists_remote(branch, remote="origin"):
    return branch in list_remote_branches(remote)

def choose_primary_branch():
    # prefer develop, then main, then master, else first local branch (not current)
    locals_ = list_local_branches()
    candidates = ["develop", "main", "master"]
    for c in candidates:
        if c in locals_:
            return c
    return locals_[0] if locals_ else None

def is_merged_into(source, target):
    """Return True if source is an ancestor of target (i.e., fully merged)."""
    cp = run_git(["merge-base", "--is-ancestor", source, target])
    return cp.returncode == 0

def show_commits_unique(source, target):
    """Show commits in source that are not in target (target..source)."""
    cp = run_git(["log", "--oneline", f"{target}..{source}"])
    if cp.returncode != 0:
        return cp.stderr.strip()
    return cp.stdout.strip() or "(no unique commits)"

def create_backup_tag(branch, repo_root):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_tag = f"backup/{branch}/{ts}"
    cp = run_git(["tag", safe_tag, branch])
    if cp.returncode != 0:
        print(f"❌ Failed to create tag {safe_tag}: {cp.stderr.strip()}")
        return None
    print(f"✅ Created backup tag: {safe_tag}")
    log_action(repo_root, f"Created backup tag {safe_tag} for branch {branch}")
    if branch_exists_remote(branch):
        if confirm("Push the backup tag to 'origin'?"):
            cp2 = run_git(["push", "origin", safe_tag])
            if cp2.returncode == 0:
                print(f"✅ Pushed tag {safe_tag} to origin")
                log_action(repo_root, f"Pushed tag {safe_tag} to origin")
            else:
                print(f"❌ Failed to push tag: {cp2.stderr.strip()}")
    return safe_tag

def is_working_tree_clean():
    cp = run_git(["status", "--porcelain"])
    if cp.returncode != 0:
        # If git status failed, treat as not clean to be safe
        return False
    return cp.stdout.strip() == ""

# ---------------- Setup & Basic Commands ----------------
def setup_repo():
    suggested_dir = os.path.expanduser("~/my_project")
    print(f"Suggested directory: {suggested_dir}")
    target_dir = input("Enter repo directory path (or press Enter for suggested): ").strip()
    if not target_dir:
        target_dir = suggested_dir
    os.makedirs(target_dir, exist_ok=True)
    os.chdir(target_dir)
    if confirm("Initialize new Git repository here?"):
        print_run_git(["init"])
    remote_url = input("Enter GitHub repository URL (leave blank to skip): ").strip()
    if remote_url:
        print_run_git(["remote", "add", "origin", remote_url])
        print(f"✅ Remote 'origin' set to {remote_url}")

def check_git_repo():
    cp = run_git(["rev-parse", "--is-inside-work-tree"])
    if cp.returncode != 0:
        print("❌ Not inside a Git repository. Run setup first.")
        return False
    return True

def create_branch():
    if not check_git_repo(): return
    name = input("Enter new branch name: ").strip()
    if not name:
        print("❌ Branch name cannot be empty.")
        return
    print_run_git(["checkout", "-b", name])
    if confirm("Push new branch to remote?"):
        print_run_git(["push", "-u", "origin", name])

def commit_changes():
    if not check_git_repo(): return
    msg = input("Commit message: ").strip()
    if not msg:
        print("❌ Commit message cannot be empty.")
        return
    print_run_git(["add", "."])
    print_run_git(["commit", "-m", msg])
    if confirm("Push changes to remote?"):
        print_run_git(["push"])

def merge_branch():
    if not check_git_repo(): return
    target = input("Merge into branch (e.g., develop): ").strip()
    source = input("Branch to merge from: ").strip()
    if not target or not source:
        print("❌ Branch names cannot be empty.")
        return
    if confirm(f"Merge '{source}' into '{target}'?"):
        print_run_git(["checkout", target])
        print_run_git(["pull"])
        print_run_git(["merge", source])
        if confirm("Push merged changes to remote?"):
            print_run_git(["push"])

def pull_latest():
    if not check_git_repo(): return
    print_run_git(["pull"])

# ---------------- Read-only View Commands ----------------
def show_status():
    """Show concise git status with branch info (read-only)."""
    if not check_git_repo():
        return
    print("\n🔎 Git status (short + branch):")
    # short output is easiest to scan; includes branch header with --branch
    print_run_git(["status", "--short", "--branch"])

def show_branches():
    """Show local and remote branches and upstream info (read-only)."""
    if not check_git_repo():
        return
    print("\n🌿 Local branches (-vv):")
    print_run_git(["branch", "-vv"])           # local branches with upstream & last commit
    print("\n🌐 Remote branches:")
    print_run_git(["branch", "-r"])            # remote-only branches
    print("\n🗂 All branches (local + remote):")
    print_run_git(["branch", "-a"])            # all branches

def show_history():
    """Show commit graph (read-only). Prompts for number of commits to display."""
    if not check_git_repo():
        return
    num = input("How many commits to show (Enter for 100): ").strip()
    try:
        n = int(num) if num else 100
    except ValueError:
        n = 100
    print(f"\n📜 Last {n} commits (graph view):")
    print_run_git(["log", "--oneline", "--graph", "--decorate", "--all", f"-n{n}"])


# ---------------- Delete Branch (SAFE) ----------------
def delete_branch():
    if not check_git_repo(): return
    repo_root = get_repo_root()
    current = get_current_branch()
    print(f"Current branch: {current}")
    print("Delete branch options:")
    print("  1) Delete local branch")
    print("  2) Delete remote branch (origin)")
    print("  3) Delete both local and remote")
    choice = input("> ").strip()
    if choice not in {"1","2","3"}:
        print("❌ Invalid choice.")
        return

    branch = input("Branch name to delete: ").strip()
    if not branch:
        print("❌ Branch name cannot be empty.")
        return

    # Protect very important branches
    if branch in PROTECTED_BRANCHES:
        print(f"⚠️  '{branch}' is a protected branch by default.")
        confirm_phrase = f"DELETE {branch}"
        print(f"To proceed you must type exactly: {confirm_phrase}")
        if not typed_confirm("Protected-branch deletion confirmation", confirm_phrase):
            print("Aborted protected-branch deletion.")
            return

    # Local delete flow
    if choice in {"1","3"}:
        if not branch_exists_local(branch):
            print(f"ℹ️ Local branch '{branch}' not found.")
        else:
            if branch == current:
                print("❌ You are currently on the branch you want to delete.")
                safe_target = choose_primary_branch()
                if safe_target:
                    print(f"Suggested safe branch to switch to: {safe_target}")
                if confirm("Switch to the suggested safe branch and continue?"):
                    print_run_git(["checkout", safe_target])
                else:
                    print("Abort: please checkout a different branch before deleting.")
                    return

            # Determine merge safety
            primary = choose_primary_branch()
            if primary and is_merged_into(branch, primary):
                print(f"✅ Branch '{branch}' appears merged into '{primary}'. Safe to delete locally.")
                if confirm(f"Delete local branch '{branch}'?"):
                    cp = run_git(["branch", "-d", branch])
                    if cp.returncode == 0:
                        print(f"✅ Deleted local branch '{branch}'.")
                        log_action(repo_root, f"Deleted local branch {branch}")
                    else:
                        print(f"❌ Failed to delete locally: {cp.stderr.strip()}")
            else:
                # Unmerged / unknown safety
                if primary:
                    print(f"⚠️ Branch '{branch}' does NOT appear merged into '{primary}'.")
                else:
                    print("⚠️ Could not determine a primary branch to check merge status.")
                commits = show_commits_unique(branch, primary or "HEAD")
                print("\nCommits that are unique to the branch (would be lost):")
                print(commits)
                if confirm("Create a backup tag for this branch before deleting?"):
                    tag = create_backup_tag(branch, repo_root)
                    if tag:
                        print(f"Backup tag created: {tag}")
                # require exact-branch typed confirmation for force delete
                print("To force-delete this unmerged local branch, you must type the exact branch name.")
                if typed_confirm("Force-delete confirmation", branch):
                    cp = run_git(["branch", "-D", branch])
                    if cp.returncode == 0:
                        print(f"✅ Force-deleted local branch '{branch}'.")
                        log_action(repo_root, f"Force-deleted local branch {branch}")
                    else:
                        print(f"❌ Failed to force-delete: {cp.stderr.strip()}")
                else:
                    print("Aborted local deletion.")

    # Remote delete flow
    if choice in {"2","3"}:
        # ensure remote exists
        cp_rem = run_git(["remote"])
        remotes = cp_rem.stdout.split() if cp_rem.returncode == 0 else []
        if "origin" not in remotes:
            print("❌ Remote 'origin' not configured; cannot delete remote branch.")
            return
        if not branch_exists_remote(branch, "origin"):
            print(f"ℹ️ Remote branch 'origin/{branch}' not found.")
            # allow user to still try deletion?
            if not confirm("Do you still want to attempt remote deletion?"):
                return

        # Extra safety for remote delete (require exact typed match)
        print("To delete the remote branch, type the exact branch name to confirm.")
        if not typed_confirm("Remote-delete confirmation", branch):
            print("Aborted remote deletion.")
            return

        cp = run_git(["push", "origin", "--delete", branch])
        if cp.returncode == 0:
            print(f"✅ Deleted remote branch 'origin/{branch}'.")
            log_action(repo_root, f"Deleted remote branch origin/{branch}")
        else:
            print(f"❌ Failed to delete remote branch: {cp.stderr.strip()}")

# ---------------- Push Staging -> Main (SAFE) ----------------
def push_staging_to_main():
    """Merge staging into main and push with strong safeguards."""
    if not check_git_repo(): return
    repo_root = get_repo_root()

    # check availability of branches locally or remotely
    staging_local = branch_exists_local("staging")
    main_local = branch_exists_local("main") or branch_exists_local("master")

    staging_remote = branch_exists_remote("staging", "origin")
    main_remote = branch_exists_remote("main", "origin") or branch_exists_remote("master", "origin")

    if not staging_local and staging_remote:
        if confirm("Local 'staging' not found. Create tracking branch from origin/staging?"):
            cp = run_git(["checkout", "-b", "staging", "origin/staging"])
            if cp.returncode != 0:
                print("❌ Failed to create local staging from origin/staging.")
                return
            staging_local = True

    if not main_local and main_remote:
        # prefer 'main' over 'master' if both exist remotely
        remote_main = "main" if branch_exists_remote("main", "origin") else "master"
        if confirm(f"Local main/master not found. Create tracking branch from origin/{remote_main}?"):
            cp = run_git(["checkout", "-b", remote_main, f"origin/{remote_main}"])
            if cp.returncode != 0:
                print(f"❌ Failed to create local {remote_main} from origin/{remote_main}.")
                return
            main_local = True

    if not (staging_local or staging_remote):
        print("❌ No staging branch found locally or on origin. Aborting.")
        return
    if not (main_local or main_remote):
        print("❌ No main/master branch found locally or on origin. Aborting.")
        return

    # Ensure working tree is clean
    if not is_working_tree_clean():
        print("⚠️ Working tree is not clean. Please commit or stash changes before deploying to main.")
        if not confirm("Proceed despite uncommitted changes?"):
            print("Aborted due to dirty working tree.")
            return

    # Pull latest for both branches
    print_run_git(["checkout", "staging"])
    print_run_git(["pull", "origin", "staging"])
    # switch to chosen main (prefer main over master)
    chosen_main = "main" if branch_exists_local("main") or branch_exists_remote("main") else "master"
    print_run_git(["checkout", chosen_main])
    print_run_git(["pull", "origin", chosen_main])

    # Optional backup tag on main
    if confirm(f"Create a backup tag for '{chosen_main}' before merging?"):
        tag = create_backup_tag(chosen_main, repo_root)
        if tag:
            print(f"Backup tag created: {tag}")

    # Require typed confirmation
    confirm_phrase = "PUSH STAGING TO MAIN"
    print(f"⚠️ This will merge 'staging' into '{chosen_main}' and push to origin.")
    print(f"To confirm, type exactly: {confirm_phrase}")
    if not typed_confirm("Final confirmation", confirm_phrase):
        print("Aborted push staging->main.")
        return

    # Perform merge
    cp = run_git(["merge", "staging"])
    if cp.returncode != 0:
        print("❌ Merge failed or produced conflicts. Resolve manually, then push. Aborting push.")
        if cp.stderr:
            print(cp.stderr.strip())
        return

    # Push to origin
    cp2 = run_git(["push", "origin", chosen_main])
    if cp2.returncode == 0:
        print(f"✅ Successfully pushed '{chosen_main}' to origin.")
        log_action(repo_root, f"Merged staging into {chosen_main} and pushed to origin")
    else:
        print(f"❌ Failed to push {chosen_main}: {cp2.stderr.strip()}")

# ---------------- Menu ----------------
def menu():
    if not git_available():
        print("❌ 'git' executable not found in PATH. Please ensure git is installed.")
        sys.exit(1)

    while True:
        print("\n📌 Senior DevOps Git Helper — Safe Mode")
        print("1. Setup new repo")
        print("2. Create & push new branch")
        print("3. Commit & push changes")
        print("4. Merge branch into another")
        print("5. Pull latest changes")
        print("6. Git status (view)")
        print("7. Show branches (local & remote)")
        print("8. Show commit history (graph)")
        print("9. Delete branch (SAFE)")
        print("10. Push staging -> main (SAFE)")
        print("11. Exit")
        choice = input("> ").strip()

        if choice == "1":
            setup_repo()
        elif choice == "2":
            create_branch()
        elif choice == "3":
            commit_changes()
        elif choice == "4":
            merge_branch()
        elif choice == "5":
            pull_latest()
        elif choice == "6":
            show_status()
        elif choice == "7":
            show_branches()
        elif choice == "8":
            show_history()
        elif choice == "9":
            delete_branch()
        elif choice == "10":
            push_staging_to_main()
        elif choice == "11":
            print("👋 Exiting Git Helper.")
            break
        else:
            print("❌ Invalid choice.")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nInterrupted. Bye.")
