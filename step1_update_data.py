import subprocess
import sys
import argparse
import os
import json
import base64

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def compute_stats_before(names_set):
    houses = load_json("data/houses.json") or []
    existing_active = set(
        h["username"] for h in houses
        if "username" in h and not h.get("abandoned", False)
    )
    newcomers_set = names_set - existing_active
    newcomers = len(newcomers_set)
    newly_abandoned = len(existing_active - names_set)
    old_active = len(existing_active)
    new_active = len(names_set)
    newcomer_names_str = ",".join(list(newcomers_set))
    return old_active, new_active, newcomers, newly_abandoned, newcomer_names_str

def run_step(cmd):
    print(f"\n[{' '.join(cmd)}]")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print("\n❌ Step failed! Stopping pipeline.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Step 1: Fetch followers and update city data")
    parser.add_argument("target", help="Target Instagram username (e.g. thefollowerstown_official)")
    parser.add_argument("--delay", nargs=2, default=["2", "5"], help="Delay for fetching followers")
    args = parser.parse_args()

    print("==================================================")
    print("🚀 STEP 1: GATHERING DATA & UPDATING CITY")
    print("==================================================")

    # 0. Check for Session in Secrets (Base64)
    session_b64 = os.environ.get("IG_SESSION_B64")
    if session_b64:
        print("🔑 Found IG_SESSION_B64 secret. Decoding to session.json...")
        try:
            session_data = base64.b64decode(session_b64)
            with open("session.json", "wb") as f:
                f.write(session_data)
            print("✅ session.json created successfully.")
        except Exception as e:
            print(f"❌ Failed to decode IG_SESSION_B64: {e}")
            sys.exit(1)
    else:
        if not os.path.exists("session.json"):
            print("⚠️ Warning: IG_SESSION_B64 not found and session.json does not exist.")
            print("   Make sure session.json is present or IG_SESSION_B64 is set in your secrets.")

    # 1. Fetch Followers
    run_step([sys.executable, "scripts/fetch_followers.py", args.target, "--delay", str(args.delay[0]), str(args.delay[1])])
    
    # Read the names we just fetched
    try:
        with open("followers.txt", "r", encoding="utf-8") as f:
            content = f.read()
        names_set = set(n.strip() for n in content.replace(",", "\n").split("\n") if n.strip())
    except Exception as e:
        print(f"❌ Failed to read followers.txt: {e}")
        sys.exit(1)

    # 2. Calculate Stats BEFORE mutating the house data
    old_active, new_active, newcomers, newly_abandoned, newcomer_names_str = compute_stats_before(names_set)
    
    stats = {
        "old_active": old_active,
        "new_active": new_active,
        "newcomers": newcomers,
        "newly_abandoned": newly_abandoned,
        "newcomer_names_str": newcomer_names_str
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/daily_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f)
        
    print(f"\n  📊  Stats preview:")
    print(f"      Population:  {old_active} → {new_active}")
    print(f"      Newcomers:   +{newcomers}")
    print(f"      Left:        -{newly_abandoned}")

    # 3. Update Houses Data
    run_step([sys.executable, "scripts/fetch_houses.py", "followers.txt"])
    
    print("\n==================================================")
    print("✅ STEP 1 COMPLETE!")
    print("==================================================")
    print("Data has been updated and stats saved to data/daily_stats.json.")
    print("The changes should now trigger a deployment to your live website.")
    print("\n⏳ Please WAIT for the website to fully update before running step2_make_video.py!")

if __name__ == "__main__":
    main()
