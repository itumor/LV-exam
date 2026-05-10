#!/usr/bin/env python3
"""
Auto-create PRs from completed tasks in Multica.

This script:
1. Finds completed Multica issues that don't have associated PRs
2. Creates GitHub branches for each completed issue
3. Commits any changes related to the issue
4. Opens PRs targeting the main branch
5. Links the PR back to the Multica issue

Requirements:
- multica CLI installed and authenticated
- gh CLI installed and authenticated
- Repository already checked out
"""

import json
import subprocess
import sys
import os
import re
from datetime import datetime

def run_command(cmd, capture_output=True, check=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=capture_output, 
            text=True, 
            check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture_output:
            print(f"Command failed: {cmd}")
            print(f"Error: {e.stderr}")
        raise

def get_completed_issues():
    """Get all completed issues from Multica."""
    cmd = "multica issue list --status done --output json"
    result = run_command(cmd)
    issues = json.loads(result.stdout)
    return issues.get('issues', [])

def get_issue_pr(issue_id):
    """Check if an issue already has an associated PR."""
    # Check issue comments for PR links
    cmd = f"multica issue comment list {issue_id} --output json"
    result = run_command(cmd)
    comments = json.loads(result.stdout)  # This is a list directly
    
    for comment in comments:  # Iterate directly over the list
        if 'github.com' in comment.get('content', '') and '/pull/' in comment.get('content', ''):
            # Extract PR URL
            match = re.search(r'https://github\.com/[^/]+/[^/]+/pull/\d+', comment['content'])
            if match:
                return match.group(0)
    return None

def get_git_changes_since(issue_updated_at):
    """Get git changes since the issue was last updated."""
    # Get commits since the issue was updated
    cmd = f"git log --since='{issue_updated_at}' --pretty=format:'%H'"
    result = run_command(cmd, check=False)
    if result.returncode != 0:
        return []
    
    commits = result.stdout.strip().split('\n') if result.stdout.strip() else []
    return commits

def create_pr_for_issue(issue):
    """Create a PR for a completed Multica issue."""
    issue_id = issue['id']
    issue_title = issue['title']
    issue_number = issue['identifier']  # e.g., HUM-132
    
    print(f"Processing issue: {issue_number} - {issue_title}")
    
    # Check if PR already exists
    existing_pr = get_issue_pr(issue_id)
    if existing_pr:
        print(f"  PR already exists: {existing_pr}")
        return existing_pr
    
    # Create branch name from issue
    safe_title = re.sub(r'[^\w\s-]', '', issue_title).strip().lower()
    safe_title = re.sub(r'[-\s]+', '-', safe_title)
    branch_name = f"auto-pr/{issue_number}-{safe_title[:50]}"
    
    # Check if branch already exists
    result = run_command(f"git show-ref --verify --quiet refs/heads/{branch_name}", check=False)
    if result.returncode == 0:
        print(f"  Branch {branch_name} already exists")
        # Checkout existing branch
        run_command(f"git checkout {branch_name}")
    else:
        # Create new branch from main
        run_command("git checkout main")
        run_command("git pull origin main")
        run_command(f"git checkout -b {branch_name}")
        print(f"  Created branch: {branch_name}")
    
    # Check if there are any changes to commit
    result = run_command("git status --porcelain", check=False)
    if not result.stdout.strip():
        print(f"  No changes to commit for issue {issue_number}")
        run_command("git checkout main")
        return None
    
    # Add all changes
    run_command("git add -A")
    
    # Create commit message
    commit_message = f"""{issue_number}: {issue_title}

Auto-generated commit from Multica issue {issue_number}.

This commit implements the work described in the Multica issue and prepares
a pull request for review.

Issue: {issue_number}
Title: {issue_title}
"""
    
    run_command(f'git commit -m "{commit_message}"')
    print(f"  Committed changes for issue {issue_number}")
    
    # Push branch to origin
    run_command(f"git push -u origin {branch_name}")
    print(f"  Pushed branch {branch_name} to origin")
    
    # Create PR using gh CLI
    pr_body = f"""## Summary

This PR implements the work from Multica issue [{issue_number}](https://multica.ai/app/workspaces/171c2f75-7788-47d2-85aa-e5753bc2925b/issues/{issue_id}).

### Description
{issue_title}

### Related Issue
- Multica Issue: [{issue_number}](https://multica.ai/app/workspaces/171c2f75-7788-47d2-85aa-e5753bc2925b/issues/{issue_id})

### Checklist
- [ ] Code implements the requirements from the Multica issue
- [ ] Tests have been added or updated as needed
- [ ] Documentation has been updated if necessary
- [ ] Code follows project conventions and style guides

*This PR was auto-generated by the Multica DevOps Automation Agent.*"""
    
    pr_result = run_command(f'''gh pr create \
        --title "{issue_number}: {issue_title}" \
        --body "{pr_body}" \
        --base main \
        --head {branch_name}''')
    
    pr_url = pr_result.stdout.strip()
    print(f"  Created PR: {pr_url}")
    
    # Add comment to Multica issue with PR link
    comment_content = f"""Automatically created PR: {pr_url}

This PR implements the work from Multica issue {issue_number}: {issue_title}

The PR is ready for review and merges into the main branch."""
    
    run_command(f'''multica issue comment add {issue_id} --content-stdin <<'EOF'
{comment_content}
EOF''')
    
    # Return to main branch
    run_command("git checkout main")
    
    return pr_url

def main():
    """Main function to create PRs from completed tasks."""
    print("Starting auto-PR creation from completed Multica tasks...")
    
    # Ensure we're in a git repository
    if not os.path.exists(".git"):
        print("Error: This script must be run from a git repository")
        sys.exit(1)
    
    # Get completed issues
    issues = get_completed_issues()
    print(f"Found {len(issues)} completed issues")
    
    # Process each issue
    prs_created = 0
    for issue in issues:
        # Skip if issue is very old (optional)
        # updated_at = datetime.fromisoformat(issue['updated_at'].replace('Z', '+00:00'))
        # if (datetime.now() - updated_at).days > 30:
        #     continue
        
        pr_url = create_pr_for_issue(issue)
        if pr_url:
            prs_created += 1
    
    print(f"\nCompleted! Created {prs_created} PRs from completed Multica issues.")
    
    # Summary
    if prs_created > 0:
        print("\nNext steps:")
        print("1. Review the created PRs")
        print("2. Run tests and verify functionality")
        print("3. Approve and merge PRs that are ready")
        print("4. Delete merged branches")

if __name__ == "__main__":
    main()
