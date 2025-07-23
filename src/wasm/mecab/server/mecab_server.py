#!/usr/bin/env python3
"""
MeCab Dictionary Server
Provides server-side MeCab processing with full NAIST-JDIC dictionary
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import MeCab
import json
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize MeCab with full dictionary
try:
    # Try to use system MeCab with NAIST-JDIC
    mecab = MeCab.Tagger()
except:
    # Fallback to basic MeCab
    mecab = MeCab.Tagger('-Owakati')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'mecab-server'})

@app.route('/parse', methods=['POST'])
def parse():
    """Parse Japanese text using MeCab"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Parse with MeCab
        result = mecab.parse(text)
        
        return jsonify({
            'text': text,
            'result': result,
            'mode': 'full-dictionary'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/parse_detailed', methods=['POST'])
def parse_detailed():
    """Parse Japanese text and return detailed token information"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Parse with MeCab
        parsed = mecab.parse(text)
        lines = parsed.strip().split('\n')
        
        tokens = []
        for line in lines:
            if line == 'EOS' or not line:
                break
                
            parts = line.split('\t')
            if len(parts) < 2:
                continue
                
            surface = parts[0]
            features = parts[1].split(',')
            
            token = {
                'surface': surface,
                'pos': features[0] if len(features) > 0 else '*',
                'pos1': features[1] if len(features) > 1 else '*',
                'pos2': features[2] if len(features) > 2 else '*',
                'pos3': features[3] if len(features) > 3 else '*',
                'pos4': features[4] if len(features) > 4 else '*',
                'pos5': features[5] if len(features) > 5 else '*',
                'inflection': features[6] if len(features) > 6 else '*',
                'reading': features[7] if len(features) > 7 else surface,
                'pronunciation': features[8] if len(features) > 8 else (features[7] if len(features) > 7 else surface)
            }
            tokens.append(token)
        
        return jsonify({
            'text': text,
            'tokens': tokens,
            'mode': 'full-dictionary'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/wakati', methods=['POST'])
def wakati():
    """Perform word segmentation (wakati-gaki)"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Create wakati tagger
        wakati_tagger = MeCab.Tagger('-Owakati')
        result = wakati_tagger.parse(text).strip()
        
        return jsonify({
            'text': text,
            'result': result,
            'mode': 'full-dictionary'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reading', methods=['POST'])
def reading():
    """Get reading (yomi) for text"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Parse and extract readings
        parsed = mecab.parse(text)
        lines = parsed.strip().split('\n')
        
        readings = []
        for line in lines:
            if line == 'EOS' or not line:
                break
                
            parts = line.split('\t')
            if len(parts) < 2:
                continue
                
            features = parts[1].split(',')
            reading = features[7] if len(features) > 7 else parts[0]
            readings.append(reading)
        
        return jsonify({
            'text': text,
            'reading': ''.join(readings),
            'mode': 'full-dictionary'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)