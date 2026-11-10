/* ExtendScript baseline: export the visible PSD/PSB composite to a PNG copy.
 * ADOBE_JOB is supplied as JSON literals by the trusted local adapter.
 * No source document is saved. No open user document is closed or modified.
 * Require Photoshop to be idle with all documents closed before starting.
 */
(function () {
    var source = null;
    var copy = null;
    var oldDialogs = app.displayDialogs;
    var failure = null;
    function marker(text) {
        var f = new File(ADOBE_JOB.marker);
        f.encoding = "UTF-8";
        f.lineFeed = "Unix";
        if (!f.open("w")) { throw new Error("Cannot write completion marker: " + f.error); }
        try { f.write(text); } finally { f.close(); }
    }
    try {
        if (app.documents.length !== 0) {
            throw new Error("Close all Photoshop documents before running the worker; no existing document was touched.");
        }
        var input = new File(ADOBE_JOB.input);
        var output = new File(ADOBE_JOB.output);
        if (!input.exists) { throw new Error("Input file is missing."); }
        if (output.exists) { throw new Error("Output already exists; refusing to overwrite."); }
        app.displayDialogs = DialogModes.NO;
        source = app.open(input);
        if (source.mode !== DocumentMode.RGB && source.mode !== DocumentMode.GRAYSCALE) {
            throw new Error("Baseline PNG export supports RGB or grayscale only; no color-mode conversion was performed.");
        }
        if (source.bitsPerChannel !== BitsPerChannelType.EIGHT && source.bitsPerChannel !== BitsPerChannelType.SIXTEEN) {
            throw new Error("Baseline PNG export supports 8-bit or 16-bit documents only; no bit-depth conversion was performed.");
        }
        copy = source.duplicate("Adobe worker export copy");
        var png = new PNGSaveOptions();
        png.interlaced = false;
        png.compression = 6;
        // PNG writes a composite. Do not call flatten(), which removes alpha.
        copy.saveAs(output, png, true, Extension.LOWERCASE);
        if (!output.exists || output.length === 0) { throw new Error("PNG output is missing or empty."); }
    } catch (error) {
        failure = String(error);
    } finally {
        if (copy !== null) {
            try { copy.close(SaveOptions.DONOTSAVECHANGES); }
            catch (closeCopyError) { failure = failure || String(closeCopyError); }
        }
        if (source !== null) {
            try { source.close(SaveOptions.DONOTSAVECHANGES); }
            catch (closeSourceError) { failure = failure || String(closeSourceError); }
        }
        try { app.displayDialogs = oldDialogs; }
        catch (restoreError) { failure = failure || String(restoreError); }
    }
    if (failure !== null) {
        marker("ERROR\n" + failure + "\n");
        return "ERROR";
    }
    marker("OK\n");
    return "OK";
}());
