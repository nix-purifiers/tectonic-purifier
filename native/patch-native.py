from pathlib import Path

file = Path("crates/bundles/src/lib.rs")
text = file.read_text()
needle = """    use url::Url;

    // Parse URL and detect bundle type"""
assert text.count(needle) == 1
text = text.replace(
    needle,
    """    use url::Url;

    let source = std::env::var("TECTONIC_PURIFIER_BUNDLE").unwrap_or(source);

    // Parse URL and detect bundle type""",
)
file.write_text(text)

file = Path("crates/bundles/src/itar.rs")
text = file.read_text()
needle = """    fn get_index_reader(&mut self) -> Result<Box<dyn Read>> {
        let mut geturl_backend"""
assert text.count(needle) == 1
text = text.replace(
    needle,
    """    fn get_index_reader(&mut self) -> Result<Box<dyn Read>> {
        if let Some(path) = std::env::var_os("TECTONIC_PURIFIER_INDEX_FILE") {
            return Ok(Box::new(std::fs::File::open(path)?));
        }
        let mut geturl_backend""",
)
file.write_text(text)
