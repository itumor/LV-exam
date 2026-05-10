#!/bin/bash
#
# Multica Workflow Shortcuts
# CLI-first delivery agent utilities for Multica and GitHub alignment
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Check if multica is available
if ! command -v multica &> /dev/null; then
    log_error "multica CLI not found. Please install multica CLI first."
    exit 1
fi

# Check if gh is available
if ! command -v gh &> /dev/null; then
    log_error "gh CLI not found. Please install GitHub CLI first."
    exit 1
fi

# Verify authentication
verify_auth() {
    log_info "Verifying Multica authentication..."
    if ! multica auth status > /dev/null 2>&1; then
        log_error "Multica authentication failed. Please run 'multica login'"
        return 1
    fi
    
    log_info "Verifying GitHub authentication..."
    if ! gh auth status > /dev/null 2>&1; then
        log_error "GitHub authentication failed. Please run 'gh auth login'"
        return 1
    fi
    
    log_success "Authentication verified"
    return 0
}

# Get workspace info
get_workspace_info() {
    multica workspace get --output json
}

# List assigned issues
list_assigned_issues() {
    local agent_name="$1"
    multica issue list --assignee "$agent_name" --output json
}

# Create issue
create_issue() {
    local title="$1"
    local description="$2"
    local priority="${3:-medium}"
    local status="${4:-todo}"
    
    multica issue create \
        --title "$title" \
        --description-stdin <<< "$description" \
        --priority "$priority" \
        --status "$status"
}

# Update issue status
update_issue_status() {
    local issue_id="$1"
    local status="$2"
    
    multica issue status "$issue_id" "$status"
}

# Add comment to issue
add_issue_comment() {
    local issue_id="$1"
    local comment="$2"
    
    multica issue comment add "$issue_id" --content-stdin <<< "$comment"
}

# Create GitHub branch
create_github_branch() {
    local branch_name="$1"
    local base_branch="${2:-main}"
    
    git checkout "$base_branch"
    git pull origin "$base_branch"
    git checkout -b "$branch_name"
}

# Push branch and create PR
create_pr() {
    local branch_name="$1"
    local title="$2"
    local body="$3"
    local base_branch="${4:-main}"
    
    git push -u origin "$branch_name"
    
    gh pr create \
        --title "$title" \
        --body "$body" \
        --base "$base_branch" \
        --head "$branch_name"
}

# Main command router
case "${1:-}" in
    auth:verify)
        verify_auth
        ;;
    ws:info)
        get_workspace_info
        ;;
    issue:list)
        shift
        list_assigned_issues "$@"
        ;;
    issue:create)
        if [ $# -lt 2 ]; then
            log_error "Usage: $0 issue:create <title> <description> [priority] [status]"
            exit 1
        fi
        create_issue "$2" "$3" "${4:-medium}" "${5:-todo}"
        ;;
    issue:status)
        if [ $# -lt 2 ]; then
            log_error "Usage: $0 issue:status <issue_id> <status>"
            exit 1
        fi
        update_issue_status "$2" "$3"
        ;;
    issue:comment)
        if [ $# -lt 2 ]; then
            log_error "Usage: $0 issue:comment <issue_id> <comment>"
            exit 1
        fi
        add_issue_comment "$2" "$3"
        ;;
    git:branch)
        if [ $# -lt 2 ]; then
            log_error "Usage: $0 git:branch <branch_name> [base_branch]"
            exit 1
        fi
        create_github_branch "$2" "${3:-main}"
        ;;
    git:pr)
        if [ $# -lt 4 ]; then
            log_error "Usage: $0 git:pr <branch_name> <title> <body> [base_branch]"
            exit 1
        fi
        create_pr "$2" "$3" "$4" "${5:-main}"
        ;;
    *)
        cat << 'EOF'
Multica Workflow Shortcuts
========================

Usage: $0 <command> [args...]

Commands:
  auth:verify               Verify Multica and GitHub authentication
  ws:info                   Get workspace information
  issue:list [agent]        List issues assigned to agent (or all if not specified)
  issue:create <title> <description> [priority] [status]
                            Create a new Multica issue
  issue:status <issue_id> <status>
                            Update issue status (todo, in_progress, in_review, done, blocked)
  issue:comment <issue_id> <comment>
                            Add a comment to an issue
  git:branch <branch_name> [base_branch]
                            Create and checkout a new GitHub branch
  git:pr <branch_name> <title> <body> [base_branch]
                            Push branch and create a PR

Examples:
  $0 auth:verify
  $0 issue:list "Multica DevOps Automation Agent"
  $0 issue:create "Add feature X" "Description of feature X" high in_progress
  $0 issue:status HUM-123 in_review
  $0 git:branch feature/awesome-feature
  $0 git:pr feature/awesome-feature "Awesome Feature" "This PR adds an awesome feature"

EOF
        ;;
esac
