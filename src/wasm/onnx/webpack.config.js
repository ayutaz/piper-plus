import path from 'path';
import { fileURLToPath } from 'url';
import CopyWebpackPlugin from 'copy-webpack-plugin';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default {
  entry: './src/index.ts',
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
    ],
  },
  resolve: {
    extensions: ['.tsx', '.ts', '.js'],
    fallback: {
      "path": false,
      "fs": false,
      "crypto": false
    }
  },
  output: {
    filename: 'piper-onnx.js',
    path: path.resolve(__dirname, 'dist'),
    library: {
      name: 'PiperONNX',
      type: 'umd',
      export: 'default'
    },
    globalObject: 'this'
  },
  plugins: [
    new CopyWebpackPlugin({
      patterns: [
        {
          from: 'node_modules/onnxruntime-web/dist/*.wasm',
          to: '[name][ext]'
        },
        {
          from: 'node_modules/onnxruntime-web/dist/*.jsep.wasm',
          to: '[name][ext]'
        }
      ]
    })
  ],
  experiments: {
    asyncWebAssembly: true
  },
  performance: {
    maxAssetSize: 5000000,
    maxEntrypointSize: 5000000
  }
};