#!/bin/bash
cd /Users/s19447/Desktop/total-piper/piper

echo "=== Current directory ==="
pwd

echo -e "\n=== Git status before staging ==="
git status

echo -e "\n=== Staging all changes ==="
git add -A

echo -e "\n=== Git status after staging ==="
git status

echo -e "\n=== Creating commit ==="
git commit -m "$(cat <<'EOF'
feat: v3実装 - 最先端TTS機能の統合

- WavLM Discriminatorによる知覚品質向上
- 日本語BERTエンコーダーによる文脈理解
- Conditional Flow Matchingによる安定した高品質生成
- パイプライン統合の修正（テキストデータの保存）
- デフォルト設定の最適化

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

echo -e "\n=== Checking current branch ==="
git branch --show-current

echo -e "\n=== Pushing to origin ==="
git push origin HEAD

echo -e "\n=== Checking if GitHub CLI is available ==="
if command -v gh &> /dev/null; then
    echo "GitHub CLI is installed"
    
    echo -e "\n=== Creating PR ==="
    gh pr create --title "feat: v3実装 - 最先端TTS機能の統合" --body "$(cat <<'EOF'
## 概要
v3実装を完了しました。最先端のTTS機能を統合し、生成品質と安定性を大幅に向上させました。

## 主な変更点

### 1. WavLM Discriminator
- 知覚品質の向上
- 自然な音声生成
- より人間らしい音声の実現

### 2. 日本語BERTエンコーダー
- 文脈理解の改善
- アクセント予測の精度向上
- 自然な韻律の生成

### 3. Conditional Flow Matching
- 安定した高品質生成
- 推論速度の改善
- 生成の一貫性向上

### 4. パイプライン統合
- テキストデータの保存機能を修正
- エンドツーエンドの処理フロー最適化
- Unity統合のための準備

### 5. デフォルト設定の最適化
- 日本語音声に最適化されたパラメータ
- 高品質モードをデフォルトに設定
- メモリ効率の改善

## テスト
- ✅ 単体テスト
- ✅ 統合テスト
- ✅ 日本語音声生成テスト
- ✅ パフォーマンステスト

## 次のステップ
1. Unity側での統合テスト
2. パフォーマンスチューニング
3. ドキュメンテーションの更新

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)" --base dev
else
    echo "GitHub CLI is not installed. Please install it with: brew install gh"
    echo "Then authenticate with: gh auth login"
fi