import http from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const packageRoot = path.resolve(fileURLToPath(new URL("../../", import.meta.url)));
const mime = {
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".html": "text/html",
};
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
    if (pathname === "/favicon.ico") {
      res.writeHead(204).end();
      return;
    }
    let bytes;
    let type = mime[path.extname(pathname)] || "application/octet-stream";
    if (pathname === "/") {
      const html = await readFile(
        path.join(packageRoot, "test/multilingual-demo/index.html"),
        "utf8"
      );
      // Match the relative-path rewrite in the Pages deployment workflow.
      bytes = html.replaceAll("../../../", "./").replaceAll("../../", "./");
      type = "text/html";
    } else if (pathname === "/readme.html" || pathname === "/basic.html") {
      const readme = await readFile(path.join(packageRoot, "README.npm.md"), "utf8");
      const example = readme.match(/### importmap \(No Bundler\)[\s\S]*?```html\s*([\s\S]*?)```/);
      if (!example) {
        throw new Error("README importmap example missing");
      }
      let content = example[1];
      if (pathname === "/basic.html") {
        const basic = readme.match(/### Basic Usage[\s\S]*?```javascript\s*([\s\S]*?)```/);
        if (!basic) {
          throw new Error("README Basic Usage missing");
        }
        const importmap = example[1].match(/<script type="importmap">[\s\S]*?<\/script>/)[0];
        content = `${importmap}<script type="module">${basic[1]}</script>`;
      }
      bytes = `<!doctype html><html><body>${content}</body></html>`;
      type = "text/html";
    } else {
      let base = packageRoot;
      let relative = pathname.slice(1);
      if (pathname.startsWith("/g2p/")) {
        base = path.resolve(packageRoot, "../g2p");
        relative = pathname.slice(5);
      }
      if (pathname.startsWith("/ort/")) {
        base = path.join(packageRoot, "node_modules/onnxruntime-web/dist");
        relative = pathname.slice(5);
      }
      if (pathname.startsWith("/models/")) {
        base = path.join(packageRoot, "test/browser/models");
        relative = pathname.slice(8);
      }
      const file = path.resolve(base, relative);
      if (!file.startsWith(base + path.sep)) {
        res.writeHead(403).end();
        return;
      }
      bytes = await readFile(file);
    }
    res
      .writeHead(200, {
        "Content-Type": type,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      })
      .end(bytes);
  } catch (error) {
    res.writeHead(error.code === "ENOENT" ? 404 : 500).end(String(error.message));
  }
});
server.listen(4173, "127.0.0.1");
