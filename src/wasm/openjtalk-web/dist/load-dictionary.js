// Helper script to load dictionary files into the WASM file system
export async function loadDictionary(Module, dictUrl) {
    const dictFiles = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
    ];
    
    // Create directory
    try {
        Module.FS.mkdir('/dict');
    } catch (e) {
        // Directory may already exist
    }
    
    // Load each file
    for (const file of dictFiles) {
        const response = await fetch(`${dictUrl}/${file}`);
        const data = await response.arrayBuffer();
        Module.FS.writeFile(`/dict/${file}`, new Uint8Array(data));
        console.log(`Loaded: /dict/${file}`);
    }
}

export async function loadVoice(Module, voiceUrl) {
    try {
        Module.FS.mkdir('/voice');
    } catch (e) {
        // Directory may already exist
    }
    
    const response = await fetch(voiceUrl);
    const data = await response.arrayBuffer();
    Module.FS.writeFile('/voice/voice.htsvoice', new Uint8Array(data));
    console.log('Loaded voice file');
}
