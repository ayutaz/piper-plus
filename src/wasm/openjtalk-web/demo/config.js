// GitHub Pages deployment configuration
const deploymentConfig = {
    // Set to true when deploying to GitHub Pages
    isGitHubPages: false,
    
    // Base path for GitHub Pages (e.g., '/piper-plus/wasm-demo/')
    basePath: '',
    
    // Get the correct path based on deployment
    getPath: function(relativePath) {
        if (this.isGitHubPages && this.basePath) {
            // Remove leading '../' and add base path
            return this.basePath + relativePath.replace(/^\.\.\//, '');
        }
        return relativePath;
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = deploymentConfig;
}