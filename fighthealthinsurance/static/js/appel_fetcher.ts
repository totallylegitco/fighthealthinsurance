// TypeScript Version

// Import necessary modules if using a framework like jQuery or update as needed.
declare const $: any;

// DOM Elements
const outputContainer = $('#output-container');
const loadingSpinner = document.getElementById('loading-spinner');
const loadingText = document.getElementById('loading-text');
const loadingMore = document.getElementById('loading-more');

// Variables
let respBuffer = '';
let appealId = 0;
let retries = 0;
const appealsSoFar: any[] = [];

// Helper Functions
function showLoading(): void {
    if (loadingSpinner && loadingText) {
        loadingSpinner.style.display = 'block';
        loadingText.style.display = 'block';
    }
}

function hideLoading(): void {
    if (loadingSpinner && loadingText && loadingMore) {
        setTimeout(() => {
            loadingSpinner.style.display = 'none';
            loadingText.style.display = 'none';
            loadingMore.style.display = 'none';
        }, 1000);
    }
}

function processResponseChunk(chunk: string): void {
    respBuffer += chunk;
    if (respBuffer.includes('\n')) {
        const lastIndex = respBuffer.lastIndexOf('\n');
        const current = respBuffer.substring(0, lastIndex);
        respBuffer = respBuffer.substring(lastIndex + 1);

        const lines = current.split('\n');
        lines.forEach((line) => {
            if (line.trim() === '') return;

            try {
                const parsedLine = JSON.parse(line);

                if (appealsSoFar.some((appeal) => JSON.stringify(appeal) === JSON.stringify(parsedLine))) {
                    console.log('Duplicate appeal found. Skipping.');
                    return;
                }

                appealsSoFar.push(parsedLine);
                appealId++;

                // Clone and configure the form
                const clonedForm = $('#base-form').clone().prop('id', `magic${appealId}`);
                clonedForm.removeAttr('style');

                const formElement = clonedForm.find('form');
                formElement.prop('id', `form_${appealId}`);

                const submitButton = clonedForm.find('button');
                submitButton.prop('id', `submit${appealId}`);

                const appealTextElem = clonedForm.find('textarea');
                appealTextElem.text(parsedLine);
                appealTextElem.val(parsedLine);
                appealTextElem.prop('form', `form_${appealId}`);
                appealTextElem[0].setAttribute('form', `form_${appealId}`);

                outputContainer.append(clonedForm);
            } catch (error) {
                console.error('Error parsing line:', error);
            }
        });
    } else {
        console.log('Waiting for more data.');
    }
}

function doRetry(): void {
    console.log('Retrying...');
    doQuery();
}

function doQuery(): void {
    showLoading();

    $.ajax({
        url: '{% url \"appeals_json_backend\" %}',
        type: 'POST',
        data: {
            ...{% autoescape off %}{{ form_context }}{% endautoescape %},
            csrfmiddlewaretoken: '{{ csrf_token }}',
            timbit: 'is most awesomex2'
        },
        contentType: 'application/x-www-form-urlencoded',
        dataType: 'text',
        processData: true,
        xhr: function () {
            const xhr = new XMLHttpRequest();
            xhr.addEventListener('progress', (event) => {
                const chunk = event.currentTarget.responseText;
                processResponseChunk(chunk);
            });
            return xhr;
        },
        success: (response: string) => {
            console.log('AJAX success:', response);
            processResponseChunk(response);

            if (appealsSoFar.length < 3 && retries < 2) {
                retries++;
                doRetry();
            } else {
                hideLoading();
            }
        },
        error: (error: any) => {
            console.error('AJAX error:', error);
            if (retries < 2) {
                retries++;
                doRetry();
            } else {
                hideLoading();
            }
        }
    });
}

// On Document Ready
$(document).ready(doQuery);
