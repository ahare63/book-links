#!/bin/sh
# Build the read-only site and publish it to the gh-pages branch of origin.
# Leaves the current working tree alone. Use --dry-run to build and commit locally without pushing.
set -eu

dry_run=0
case "${1:-}" in
  "") ;;
  --dry-run) dry_run=1 ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: $0 [--dry-run]" >&2; exit 2; }

root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
site="$tmp/site"
wt="$tmp/worktree"
branch="publish-tmp-$$"
cleanup() {
  git -C "$root" worktree remove --force "$wt" 2>/dev/null || true
  rm -rf "$tmp"
  git -C "$root" branch -D "$branch" >/dev/null 2>&1 || true
}
trap cleanup EXIT

(cd "$root/viewer" && npm run build)
"$root/.venv/bin/book-links" --data "$root/data" build-site --out "$site"
touch "$site/.nojekyll"

if git -C "$root" ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git -C "$root" fetch origin gh-pages
  git -C "$root" worktree add --detach "$wt" FETCH_HEAD
else
  git -C "$root" worktree add --detach "$wt"
  git -C "$wt" checkout -q --orphan "$branch"
fi
git -C "$wt" rm -rfq --ignore-unmatch . >/dev/null
cp -R "$site"/. "$wt"/
git -C "$wt" add -A -f
git -C "$wt" commit -q -m "Publish site" || { echo "nothing to publish"; exit 0; }
echo "gh-pages commit: $(git -C "$wt" rev-parse --short HEAD) ($(git -C "$wt" ls-files | wc -l | tr -d ' ') files)"
if [ "$dry_run" = 1 ]; then
  echo "dry run: not pushing"
  exit 0
fi
git -C "$wt" push origin HEAD:refs/heads/gh-pages
