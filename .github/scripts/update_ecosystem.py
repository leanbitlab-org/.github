#!/usr/bin/env python3
import os
import re
import json
import urllib.request

SOURCE_README_URL = "https://raw.githubusercontent.com/LeanBitLab/LeanBitLab/main/README.md"
LOCAL_FALLBACK_SOURCE = "/home/arjun/Projects/LeanBitLab/README.md"

def fetch_source_readme():
    """Fetch the README content from LeanBitLab repository."""
    try:
        req = urllib.request.Request(
            SOURCE_README_URL,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        token = os.getenv("GITHUB_TOKEN")
        if token:
            req.add_header("Authorization", f"token {token}")
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Warning: Could not fetch from remote URL ({e}). Checking local fallback...")
        if os.path.exists(LOCAL_FALLBACK_SOURCE):
            with open(LOCAL_FALLBACK_SOURCE, "r", encoding="utf-8") as f:
                return f.read()
        raise RuntimeError("Failed to fetch source README from remote and local path not found.")

def get_repos_info():
    """Fetch repo info across LeanBitLab and leanbitlab-org."""
    urls = [
        "https://api.github.com/users/LeanBitLab/repos?per_page=100",
        "https://api.github.com/orgs/leanbitlab-org/repos?per_page=100"
    ]
    token = os.getenv("GITHUB_TOKEN")
    repos = {}
    
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            if token:
                req.add_header("Authorization", f"token {token}")
            with urllib.request.urlopen(req, timeout=8) as response:
                items = json.loads(response.read().decode())
                if isinstance(items, list):
                    for repo in items:
                        if not repo.get("fork", False):
                            name = repo["name"]
                            repos[name.lower()] = {
                                "name": name,
                                "full_name": repo["full_name"],
                                "owner": repo["owner"]["login"],
                                "stars": repo.get("stargazers_count", 0)
                            }
        except Exception as e:
            print(f"Notice: Could not fetch repos from {url} ({e})")
            
    return repos

def get_repo_downloads(full_name, token=None):
    """Fetch total downloads for all release assets of a repository."""
    total = 0
    page = 1
    while True:
        try:
            url = f"https://api.github.com/repos/{full_name}/releases?per_page=100&page={page}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            if token:
                req.add_header("Authorization", f"token {token}")
            with urllib.request.urlopen(req, timeout=8) as response:
                releases = json.loads(response.read().decode())
                if not releases:
                    break
                for r in releases:
                    for asset in r.get("assets", []):
                        total += asset.get("download_count", 0)
                if len(releases) < 100:
                    break
                page += 1
        except Exception as e:
            print(f"Notice: Could not fetch downloads for {full_name}: {e}")
            break
    return total

def format_number(num):
    if num >= 1000:
        return f"{num / 1000:.1f}k"
    return str(num)

def extract_project_rows(source_content, repos_info=None):
    """Extract table rows (<tr>...</tr>) from all project tables in source README."""
    tbody_matches = re.findall(r'<tbody>([\s\S]*?)</tbody>', source_content, re.IGNORECASE)
    all_rows = []
    
    token = os.getenv("GITHUB_TOKEN")
    downloads_cache = {}

    for tbody in tbody_matches:
        rows = re.findall(r'<tr>([\s\S]*?)</tr>', tbody, re.IGNORECASE)
        for row in rows:
            clean_row = row.strip()
            if not clean_row:
                continue

            # Update stats badges in row if repo data is available
            if repos_info:
                # Update stars badge
                def replace_stars(match):
                    repo_owner = match.group(1)
                    repo_name = match.group(2)
                    repo_key = repo_name.lower()
                    if repo_key in repos_info:
                        stars = repos_info[repo_key]["stars"]
                        formatted_stars = format_number(stars)
                        return f'<a href="https://github.com/{repo_owner}/{repo_name}/stargazers"><img src="https://img.shields.io/badge/Stars-{formatted_stars}-7C4DFF?style=flat-square&amp;labelColor=161b22" alt="Stars"></a>'
                    return match.group(0)

                clean_row = re.sub(
                    r'<a href="https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)/stargazers"><img src="https://img\.shields\.io/badge/Stars-[^-\s?]+-7C4DFF[^"]*" alt="Stars"></a>',
                    replace_stars,
                    clean_row
                )

                # Update downloads badge
                def replace_downloads(match):
                    repo_owner = match.group(1)
                    repo_name = match.group(2)
                    repo_key = repo_name.lower()
                    if repo_key in repos_info:
                        full_name = f"{repo_owner}/{repo_name}"
                        if full_name not in downloads_cache:
                            downloads_cache[full_name] = get_repo_downloads(full_name, token)
                        dl = downloads_cache[full_name]
                        formatted_dl = format_number(dl)
                        return f'<a href="https://github.com/{repo_owner}/{repo_name}/releases/latest"><img src="https://img.shields.io/badge/Downloads-{formatted_dl}-7C4DFF?style=flat-square&amp;labelColor=161b22" alt="Downloads"></a>'
                    return match.group(0)

                clean_row = re.sub(
                    r'<a href="https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)/releases/latest"><img src="https://img\.shields\.io/badge/Downloads-[^-\s?]+-7C4DFF[^"]*" alt="Downloads"></a>',
                    replace_downloads,
                    clean_row
                )

            # Format row with clean indentation
            lines = [line.strip() for line in clean_row.splitlines() if line.strip()]
            indented_row = "    <tr>\n"
            in_sub_block = False
            for line in lines:
                if line.startswith("</td>"):
                    in_sub_block = False
                    indented_row += f"      {line}\n"
                elif line.startswith("<td>"):
                    if not line.endswith("</td>") and len(line) == 4:
                        in_sub_block = True
                    indented_row += f"      {line}\n"
                elif in_sub_block:
                    indented_row += f"        {line}\n"
                else:
                    indented_row += f"      {line}\n"
            indented_row += "    </tr>"
            all_rows.append(indented_row)

    return all_rows

def build_ecosystem_table(rows):
    """Build the unified Ecosystem Projects HTML table."""
    tbody_content = "\n".join(rows)
    return f"""<table>
  <thead>
    <tr>
      <th width="32%" align="left">Project</th>
      <th width="43%" align="left">Description</th>
      <th width="25%" align="left">Stats &amp; Status</th>
    </tr>
  </thead>
  <tbody>
{tbody_content}
  </tbody>
</table>"""

def extract_sponsors_paragraph(source_content):
    """Extract sponsors paragraph from source README."""
    match = re.search(r'### 💖 (?:Active )?Sponsors[\s\S]*?(<p align="center">[\s\S]*?</p>)', source_content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def update_profile_readme(target_path="profile/README.md"):
    """Update profile/README.md with ecosystem table, support buttons, and active sponsors."""
    if not os.path.exists(target_path):
        if os.path.exists("README.md"):
            target_path = "README.md"
        else:
            raise FileNotFoundError(f"Target README not found at {target_path}")

    print(f"Reading target file: {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        target_content = f.read()

    print("Fetching source README...")
    source_content = fetch_source_readme()

    # Get live repo data if possible
    repos_info = get_repos_info()
    if repos_info:
        print(f"Found {len(repos_info)} repos for stats synchronization.")

    # 1. Update Ecosystem Projects table
    rows = extract_project_rows(source_content, repos_info)
    if rows:
        ecosystem_table = build_ecosystem_table(rows)
        ecosystem_pattern = r'(## 📱 Ecosystem Projects\s*\n\s*)(?:[\s\S]*?)(\n\s*---)'
        new_ecosystem_section = r'\g<1>' + ecosystem_table + r'\g<2>'
        target_content = re.sub(ecosystem_pattern, new_ecosystem_section, target_content, count=1)
        print(f"Ecosystem Projects table updated with {len(rows)} projects.")

    # 2. Update Support Us & GitHub Sponsors section
    support_badges = (
        '[![Open Collective Support](https://img.shields.io/badge/Support_on-Open_Collective-7FADF9?style=for-the-badge&logo=open-collective&logoColor=white)](https://opencollective.com/leanbitlab-org) '
        '[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-LeanBitLab-D32F2F?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/LeanBitLab)'
    )
    sponsors_p = extract_sponsors_paragraph(source_content)
    sponsors_block = ""
    if sponsors_p:
        sponsors_block = f"\n\n### 💖 GitHub Sponsors\n\nThank you to our amazing sponsors!\n\n{sponsors_p}"

    support_section_pattern = r'## ❤️ Support Us[\s\S]*?(?=\n---|\n## 📫|\Z)'
    new_support_section = f"""## ❤️ Support Us

Your support helps us maintain our current open-source projects and build new bloat-free experiences.

{support_badges}{sponsors_block}
"""
    target_content = re.sub(support_section_pattern, new_support_section, target_content, count=1)
    print("Support Us and GitHub Sponsors section updated.")

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(target_content)
    print(f"Successfully updated {target_path}!")

def main():
    target_path = "profile/README.md"
    if not os.path.exists(target_path) and os.path.exists("../../profile/README.md"):
        target_path = "../../profile/README.md"
    update_profile_readme(target_path)

if __name__ == "__main__":
    main()
