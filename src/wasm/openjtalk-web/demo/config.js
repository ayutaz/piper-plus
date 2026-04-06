// GitHub Pages deployment configuration for PiperPlus demo
const deploymentConfig = {
    // Set to true when deploying to GitHub Pages
    isGitHubPages: false,

    // Base path for GitHub Pages (e.g., '/piper-plus/')
    basePath: '',

    // Default model for PiperPlus.initialize()
    defaultModel: 'css10',

    // ONNX Runtime Web CDN URL
    ortCdnUrl: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js',
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = deploymentConfig;
}
