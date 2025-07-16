#!/bin/bash

# Navigate to the piper directory
cd /Users/s19447/Desktop/total-piper/piper

# Initialize git repository if not already initialized
if [ ! -d .git ]; then
    git init
fi

# Check current branch or create one
current_branch=$(git branch --show-current 2>/dev/null)
if [ -z "$current_branch" ]; then
    git checkout -b main
fi

# Add all changes
git add .

# Create commit for v3 implementation
git commit -m "feat: v3 implementation

- WavLM Discriminator実装
- 日本語BERT Encoder追加
- Conditional Flow Matching統合
- Pipeline統合の修正
- デフォルト設定の最適化

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# Show the status
echo "Current branch: $(git branch --show-current)"
echo "Git status:"
git status