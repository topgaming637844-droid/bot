const fs = require('fs');
const path = require('path');

// Mock window and document
const mockWindow = {
    location: {
        replace: function(url) {
            console.log("REDIRECTED_TO:", url);
        },
        href: "https://hglink.to/e/byra8rl00t20"
    }
};

global.window = mockWindow;
global.document = {
    location: mockWindow.location,
    getElementsByTagName: function() { return []; },
    createElement: function() { return {}; }
};

const jsContent = fs.readFileSync(path.join(__dirname, 'hglink_main.js'), 'utf8');

try {
    // Run the obfuscated JS
    eval(jsContent);
} catch (e) {
    console.error("Execution error:", e.message);
}
