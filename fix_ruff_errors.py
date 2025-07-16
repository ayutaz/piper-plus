#!/usr/bin/env python3
"""Fix remaining ruff errors in the codebase."""

import re
from pathlib import Path

def fix_blank_lines_with_whitespace(content: str) -> str:
    """Remove whitespace from blank lines."""
    # Replace lines that contain only whitespace with empty lines
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        if line.strip() == '':  # Line contains only whitespace
            fixed_lines.append('')  # Replace with empty line
        else:
            fixed_lines.append(line)
    return '\n'.join(fixed_lines)

def fix_trailing_whitespace(content: str) -> str:
    """Remove trailing whitespace from lines."""
    lines = content.split('\n')
    fixed_lines = [line.rstrip() for line in lines]
    return '\n'.join(fixed_lines)

def fix_final_newline(content: str) -> str:
    """Ensure file ends with a newline."""
    if content and not content.endswith('\n'):
        content += '\n'
    return content

def fix_unused_variable(content: str) -> str:
    """Fix unused loop variable by prefixing with underscore."""
    # Fix "for i in range" to "for _ in range" when i is not used
    content = re.sub(r'\bfor\s+i\s+in\s+range\b', 'for _ in range', content)
    return content

def fix_unused_import(content: str) -> str:
    """Remove or fix unused imports."""
    # Remove the WavLMConfig import from wavlm_discriminator.py
    content = re.sub(r'from transformers import WavLMConfig, WavLMModel', 
                     'from transformers import WavLMModel', content)
    return content

def fix_f841_error(content: str) -> str:
    """Fix unused variable assignment."""
    # Fix num_batches = len(texts) // batch_size
    content = re.sub(r'num_batches = len\(texts\) // batch_size\n', 
                     '# num_batches = len(texts) // batch_size  # Not used currently\n', content)
    return content

def process_file(file_path: Path) -> bool:
    """Process a single file and fix ruff errors."""
    try:
        content = file_path.read_text()
        original_content = content
        
        # Apply fixes
        content = fix_blank_lines_with_whitespace(content)
        content = fix_trailing_whitespace(content)
        content = fix_final_newline(content)
        
        # File-specific fixes
        if file_path.name == 'flow_matching.py':
            content = fix_unused_variable(content)
        elif file_path.name == 'wavlm_discriminator.py':
            content = fix_unused_import(content)
        elif file_path.name == 'bert_onnx_export.py':
            content = fix_f841_error(content)
        
        # Write back if changed
        if content != original_content:
            file_path.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Main function to fix ruff errors."""
    base_dir = Path('src/python/piper_train')
    
    files_to_fix = [
        'vits/bert_encoder.py',
        'vits/bert_onnx_export.py',
        'vits/flow_matching.py',
        'vits/models.py',
        'vits/wavlm_discriminator.py',
    ]
    
    fixed_count = 0
    for file_path in files_to_fix:
        full_path = base_dir / file_path
        if full_path.exists():
            if process_file(full_path):
                print(f"Fixed: {file_path}")
                fixed_count += 1
        else:
            print(f"Not found: {file_path}")
    
    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()