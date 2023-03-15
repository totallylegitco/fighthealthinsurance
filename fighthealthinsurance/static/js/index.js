import * as pdfjsLib from 'pdfjs-dist';
import Tesseract from 'tesseract.js';
function addText(text) {
    document.getElementById("denial_text").value += text;
}
const node_module_path = "/static/js/node_modules/"
const worker = await Tesseract.createWorker({
    corePath: node_module_path + "/tesseract.js-core/tesseract-core.wasm.js",
    workerPath: node_module_path + "/tesseract.js/dist/worker.min.js",
    logger: function(m){console.log(m);}
});

pdfjsLib.GlobalWorkerOptions.workerSrc = node_module_path + "pdfjs-dist/build/pdf.worker.js";

await worker.loadLanguage('eng');
await worker.initialize('eng');
await worker.setParameters({
    tessedit_pageseg_mode: Tesseract.PSM.PSM_AUTO_OSD,
});

async function getPDFPageText (pdf, pageNo) {
    const page = await pdf.getPage(pageNo);
    const tokenizedText = await page.getTextContent();
    const items = tokenizedText.items;
    const strs = items.map(token => token.str);
    const pageText = strs.join(" ");
    return pageText;
}

async function getPDFText(pdf) {
    console.log("Getting text from PDF:")
    console.log(pdf)
    const maxPages = pdf.numPages;
    console.log("Processing PDF pages:")
    console.log(maxPages)
    const pageTextPromises = [];
    for (let pageNo = 1; pageNo <= maxPages; pageNo += 1) {
	pageTextPromises.push(getPDFPageText(pdf, pageNo));
    }
    const pageTexts = await Promise.all(pageTextPromises);
    return pageTexts.join(" ");
};

function isPDF(file) {
    return file.type.match('application/pdf');
}

const recognize = async function(evt){
    const files = evt.target.files;
    const file = files[0];

    if (isPDF(file)) {
	console.log("PDF!")
	const reader = new FileReader();
	reader.onload = function () {
	    const typedarray = new Uint8Array(this.result);
	    console.log("Data?")
	    console.log(typedarray)
	    const loadingTask = pdfjsLib.getDocument(typedarray);
	    loadingTask.promise.then(doc => {
		const ret = getPDFText(doc);
		ret.then((t) => {
		    console.log("ret:");
		    console.log(ret);
		    addText(t);
		});
	    })
	};
	reader.readAsArrayBuffer(file);
    } else {
	console.log("Assuming image...")
	const ret = await worker.recognize(files[0]);
	console.log("Recognize done!")
	console.log(ret.data.text);
	addText(ret.data.text);
    }
}

const elm = document.getElementById('uploader');
if (elm != null) {
    elm.addEventListener('change', recognize);
}
