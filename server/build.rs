// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::env;
use std::fmt::Write;
use std::fs;
use std::path::PathBuf;

use anki_io::write_file_if_changed;
use anki_proto_gen::descriptors_path;
use anki_proto_gen::get_services;
use anyhow::Result;
use inflections::Inflect;
use prost_reflect::DescriptorPool;

/// Generates a lookup from the method names the web frontend posts to, to the
/// service/method indices the backend dispatches on.
fn main() -> Result<()> {
    let descriptors_path = descriptors_path();
    println!("cargo:rerun-if-changed={}", descriptors_path.display());
    let pool = DescriptorPool::decode(fs::read(descriptors_path)?.as_ref())?;
    let (_, backend_services) = get_services(&pool);

    let mut buf = String::from(
        "pub(crate) fn backend_method(name: &str) -> Option<(u32, u32)> {\n    match name {\n",
    );
    for service in &backend_services {
        for method in service.all_methods() {
            writeln!(
                buf,
                "        {:?} => Some(({}, {})),",
                method.name.to_camel_case(),
                service.index,
                method.index
            )?;
        }
    }
    buf.push_str("        _ => None,\n    }\n}\n");

    let path = PathBuf::from(env::var("OUT_DIR")?).join("methods.rs");
    write_file_if_changed(path, buf)?;
    Ok(())
}
