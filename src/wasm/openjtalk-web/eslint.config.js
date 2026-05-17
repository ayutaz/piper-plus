import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        console: "readonly",
        process: "readonly",
        Buffer: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        TextDecoder: "readonly",
        TextEncoder: "readonly",
        fetch: "readonly",
        globalThis: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        window: "readonly",
        document: "readonly",
        navigator: "readonly",
        performance: "readonly",
        AudioContext: "readonly",
        AudioWorkletProcessor: "readonly",
        AudioWorkletNode: "readonly",
        WebAssembly: "readonly",
        Worker: "readonly",
        WorkerGlobalScope: "readonly",
        self: "readonly",
        sampleRate: "readonly",
        registerProcessor: "readonly",
        currentTime: "readonly",
        currentFrame: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-console": "off",
      "prefer-const": "warn",
      "eqeqeq": "error",
      "curly": ["error", "all"],
      "no-throw-literal": "error",
    },
  },
  {
    files: ["src/audio-worklet-processor.js"],
    languageOptions: {
      globals: {
        AudioWorkletProcessor: "readonly",
        registerProcessor: "readonly",
        sampleRate: "readonly",
        currentTime: "readonly",
        currentFrame: "readonly",
      },
    },
  },
  {
    files: ["scripts/**/*.{js,mjs}"],
    languageOptions: {
      globals: {
        process: "readonly",
        Buffer: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
      },
    },
  },
  {
    // Legacy CommonJS test runners (test/*.js — direct children only; the
    // modern ESM suite lives under test/js/). They use require()/__dirname,
    // so they need the CommonJS source type and Node globals (QA finding F2).
    files: ["test/*.js"],
    languageOptions: {
      sourceType: "commonjs",
      globals: {
        require: "readonly",
        module: "readonly",
        exports: "writable",
        __dirname: "readonly",
        __filename: "readonly",
        process: "readonly",
        Buffer: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
      },
    },
  },
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "build/**",
      "demo/**",
      "models/**",
      "voices/**",
      "patches/**",
      "*.wasm",
      "*.min.js",
      "types/**",
    ],
  },
];
