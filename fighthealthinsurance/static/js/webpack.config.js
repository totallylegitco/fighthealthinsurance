const path = require('path');
const TerserPlugin = require('terser-webpack-plugin');
const CopyPlugin = require('copy-webpack-plugin');
const { BundleAnalyzerPlugin } = require('webpack-bundle-analyzer');

// Runtime worker assets that pdf.js and tesseract.js load by URL at runtime
// (they cannot be bundled). They used to be served straight out of
// /static/js/node_modules/, which stopped being published (collectstatic
// ignore + nginx deny, PR #936) -- so they are copied into dist/workers/,
// which ships with the bundles. Nothing at runtime may reference a
// node_modules URL; tests/async-unit/test_worker_assets.py pins that.
// The ONNX runtime inside the on-device OCR library, resolved the way the
// library resolves it (its own nested copy while npm keeps one, the hoisted
// one otherwise) so the files always match the build inside the library.
// Left to itself the library fetches them from a public CDN: executable code
// and a 27 MB wasm from a third party on every cold load. Published as .js
// for the same nginx reason as the workers below; qwen_webgpu_ocr.ts points
// the library here. One build, asyncify: the one with WebGPU support, which
// the model asks for (Safari, where the library would pick the plain build,
// is not offered the option; see qwen_webgpu_ocr.ts).
const transformersDir = path.join(__dirname, 'node_modules', '@huggingface', 'transformers');
const ortEntry = require.resolve('onnxruntime-web', { paths: [transformersDir] });
const ortDist = path.join(
  ortEntry.slice(0, ortEntry.lastIndexOf(path.join(path.sep, 'onnxruntime-web', path.sep))),
  'onnxruntime-web',
  'dist',
);
// `minimized` because the module is already a minified ES module with
// import.meta inside; run through the minimizer as a plain script it fails
// to parse and the build errors.
const ortRuntimeAssets = ['ort-wasm-simd-threaded.asyncify'].flatMap((build) => [
  { from: path.join(ortDist, `${build}.mjs`), to: `vendor/onnxruntime-web/${build}.js`, info: { minimized: true } },
  { from: path.join(ortDist, `${build}.wasm`), to: `vendor/onnxruntime-web/${build}.wasm` },
]);

const workerAssets = [
  // Published as .js on purpose. nginx in the web image (Debian bookworm's
  // mime.types) has no entry for .mjs, so the worker went out as
  // application/octet-stream, and browsers refuse to run a module worker or
  // dynamic import() without a JavaScript MIME type. pdf.js then fell back to
  // its "fake worker", which does the same import and failed the same way, so
  // every PDF a user attached on /scan was unreadable ("Setting up fake worker
  // failed"). Same bytes; only the extension decides the MIME type.
  // tests/async-unit/test_worker_assets.py pins the extension.
  { from: 'node_modules/pdfjs-dist/build/pdf.worker.min.mjs', to: 'workers/pdf.worker.min.js' },
  { from: 'node_modules/tesseract.js/dist/worker.min.js', to: 'workers/tesseract.js/worker.min.js' },
  { from: 'node_modules/tesseract.js-core/*.{js,wasm}', to: 'workers/tesseract.js-core/[name][ext]' },
  // The on-device OCR model's library, loaded by the page as a real ES module
  // from this origin rather than bundled: bundled, the ONNX runtime inside it
  // cannot locate its own worker and wasm (see qwen_webgpu_ocr.ts).
  { from: 'node_modules/@huggingface/transformers/dist/transformers.min.js', to: 'vendor/transformers/transformers.min.js' },
  ...ortRuntimeAssets,
];

// Check if bundle analysis is requested
const shouldAnalyze = process.env.ANALYZE === 'true';

// Only bundles a page loads; tests/sync/test_bundle_urls.py checks them against the templates.
const entryFiles = [
  'appeal.ts',
  'appeal_fetcher.ts',
  'blog.tsx',
  'blog_post.tsx',
  'chat_interface.tsx',
  'chooser.tsx',
  'entity_fetcher.ts',
  'escalation_packet_review.ts',
  'explain_denial.ts',
  'formPersistence.ts',
  'model_status.ts',
  'scrub.ts',
  'user_info_storage.ts',
];
const entries = Object.fromEntries(
  entryFiles.map((file) => [path.parse(file).name, path.join(__dirname, file)]),
);

// Determine if we're in production mode
// Production unless a developer explicitly asks for a development build.
//
// This used to test for NODE_ENV === 'production', and nothing in the repo
// ever set it: not `npm run build`, not scripts/ci_npm_build.sh,
// build_static.sh or setup_templates.sh, not the CI workflow. So every build,
// including the one collected into the deployed image, was a development
// bundle: unminified, about 3.5x the size, and -- the part that matters --
// skipping the optimization block below, whose Terser pure_funcs strip
// console.log/info/debug as a defense against logging PHI to the browser
// console. Defaulting the other way means the safe build is the one you get
// by accident. `npm run build:dev` (or NODE_ENV=development) opts out.
// isProduction is decided INSIDE the exported function, from the CLI's --mode
// when one is given, so see below.

module.exports = (env, argv) => {
  // One source of truth for mode and optimization.
  // `webpack --mode X` overrides the configured mode after this file has
  // run, so if this flag came only from NODE_ENV the two could disagree:
  // `NODE_ENV=development npm run build -- --mode production` produced
  // production-mode bundles WITHOUT the pure_funcs console stripping, under
  // a marker that said production (review). When the CLI passes a mode, it
  // decides; otherwise production unless NODE_ENV=development.
  // Whether dist/ still holds what the deploy build produced is not this
  // file's problem: scripts/build_static.sh fingerprints its own output and
  // rebuilds when the bundles changed underneath it, whoever changed them.
  const isProduction = argv && argv.mode
    ? argv.mode === 'production'
    : process.env.NODE_ENV !== 'development';
  return {
  context: __dirname,
  mode: isProduction ? 'production' : 'development',
  entry: entries,
  output: {
    path: path.resolve(__dirname, 'dist'),
    // Bundles dropped from the list would otherwise keep shipping from an old dist/.
    clean: true,
    filename: '[name].bundle.js',
    // Chunks a bundle loads itself carry their own hash, so a CDN can't
    // serve an old one; entry bundles are versioned by {% bundle %}.
    chunkFilename: '[id].[contenthash].bundle.js',
  },
  // Production optimizations
  optimization: isProduction ? {
    minimize: true,
    minimizer: [
      new TerserPlugin({
        terserOptions: {
          compress: {
            // Strip chatty console levels from production bundles as a
            // defense-in-depth against logging user health data (PHI) to the
            // browser console. console.warn/error are kept so production
            // issues stay debuggable (no browser error reporter is
            // initialized) -- never log PHI at those levels.
            pure_funcs: ['console.log', 'console.info', 'console.debug'],
          },
          format: {
            comments: false,
          },
        },
        extractComments: false,
      }),
    ],
  } : {},
  resolve: {
    modules: [
      path.resolve(__dirname, 'node_modules'),
      'node_modules'
    ],
  extensions: ['.tsx', '.ts', '.js'],
    alias: {
      '@sentry/browser': require.resolve('@sentry/browser'),
    },
  },
  module: {
    rules: [
      {
        test: /\.(ts|tsx)$/,
        use: {
          loader: 'ts-loader',
          options: {
            configFile: path.resolve(__dirname, 'tsconfig.json')
          }
        },
        exclude: /node_modules/,
      },
    ],
  },
  // Generate source maps in both development and production (OSS project, helpful for debugging)
  devtool: 'source-map',
  // Plugins - the worker asset copy always; the bundle analyzer on request
  plugins: [
    new CopyPlugin({ patterns: workerAssets }),
    ...(shouldAnalyze ? [
      new BundleAnalyzerPlugin({
        analyzerMode: 'static',
        reportFilename: 'bundle-report.html',
        openAnalyzer: true,
      }),
    ] : []),
  ],
};
}
