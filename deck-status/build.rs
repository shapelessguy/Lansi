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

/// Generates a lookup from backend method names to the service/method indices
/// the backend dispatches on and the messages they take and return, and
/// keeps a copy of the descriptors so those messages can be read as JSON.
fn main() -> Result<()> {
    let descriptors_path = descriptors_path();
    println!("cargo:rerun-if-changed={}", descriptors_path.display());
    let descriptors = fs::read(descriptors_path)?;
    let pool = DescriptorPool::decode(descriptors.as_ref())?;
    let (_, backend_services) = get_services(&pool);

    let mut buf = String::from(
        "pub(crate) fn backend_method(name: &str) -> Option<Method> {\n    match name {\n",
    );
    for service in &backend_services {
        for method in service.all_methods() {
            writeln!(
                buf,
                "        {:?} => Some(Method {{ service: {}, method: {}, input: {:?}, output: {:?} }}),",
                method.name.to_camel_case(),
                service.index,
                method.index,
                method.proto.input().full_name(),
                method.proto.output().full_name(),
            )?;
        }
    }
    buf.push_str("        _ => None,\n    }\n}\n");

    let out_dir = PathBuf::from(env::var("OUT_DIR")?);
    write_file_if_changed(out_dir.join("methods.rs"), buf)?;
    write_file_if_changed(out_dir.join("descriptors.bin"), descriptors)?;
    Ok(())
}
