use syn::{Item, ItemFn, ReturnType};

pub struct RustAstExtractor;

#[derive(Debug, Clone)]
pub struct ExtractedItem {
    pub name: String,
    pub source: String,
    pub is_test: bool,
    pub input_type: String,
    pub output_type: String,
}

impl RustAstExtractor {
    pub fn extract(code: &str) -> Vec<ExtractedItem> {
        let file = match syn::parse_file(code) {
            Ok(f) => f,
            Err(_) => return Vec::new(),
        };

        let mut results = Vec::new();

        for item in file.items {
            if let Item::Fn(ItemFn { attrs, sig, block, .. }) = item {
                let name = sig.ident.to_string();
                let is_test = attrs.iter().any(|attr| attr.path().is_ident("test")) || name.starts_with("test_");

                // Extract input parameter types
                let mut inputs = Vec::new();
                for input in &sig.inputs {
                    if let syn::FnArg::Typed(pat_type) = input {
                        inputs.push(quote::quote!(#pat_type.ty).to_string());
                    }
                }
                let input_type = if inputs.is_empty() { "()".to_string() } else { inputs.join(", ") };

                // Extract return type
                let output_type = match &sig.output {
                    ReturnType::Default => "()".to_string(),
                    ReturnType::Type(_, ty) => quote::quote!(#ty).to_string(),
                };

                let fn_token_stream = quote::quote! {
                    #sig #block
                };

                results.push(ExtractedItem {
                    name,
                    source: fn_token_stream.to_string(),
                    is_test,
                    input_type,
                    output_type,
                });
            }
        }

        results
    }
}
