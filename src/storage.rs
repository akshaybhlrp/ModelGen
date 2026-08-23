use redb::{Database, ReadableTable, TableDefinition};
use serde::{Deserialize, Serialize};
use std::path::Path;

pub const MODULES_TABLE: TableDefinition<&[u8; 32], &[u8]> = TableDefinition::new("modules");
pub const ROUTING_COUNTERS: TableDefinition<&str, u32> = TableDefinition::new("routing_counters");
pub const SIMHASH_TABLE: TableDefinition<&[u8; 32], u64> = TableDefinition::new("simhash_index");

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ModuleRecord {
    pub content_hash: [u8; 32],
    pub name: String,
    pub source_code: String,
    pub test_code: String,
    pub input_type: String,
    pub output_type: String,
    pub license: String,
    pub source_url: String,
}

pub struct PurushaDb {
    db: Database,
}

impl PurushaDb {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, redb::Error> {
        let db = Database::create(path)?;
        let write_txn = db.begin_write()?;
        {
            let _ = write_txn.open_table(MODULES_TABLE)?;
            let _ = write_txn.open_table(ROUTING_COUNTERS)?;
            let _ = write_txn.open_table(SIMHASH_TABLE)?;
        }
        write_txn.commit()?;
        Ok(Self { db })
    }

    pub fn store_module(&self, record: &ModuleRecord, simhash: u64) -> Result<(), redb::Error> {
        let serialized = serde_json::to_vec(record).unwrap();
        let write_txn = self.db.begin_write()?;
        {
            let mut mod_table = write_txn.open_table(MODULES_TABLE)?;
            mod_table.insert(&record.content_hash, serialized.as_slice())?;

            let mut sim_table = write_txn.open_table(SIMHASH_TABLE)?;
            sim_table.insert(&record.content_hash, simhash)?;
        }
        write_txn.commit()?;
        Ok(())
    }

    pub fn get_module(&self, hash: &[u8; 32]) -> Result<Option<ModuleRecord>, redb::Error> {
        let read_txn = self.db.begin_read()?;
        let mod_table = read_txn.open_table(MODULES_TABLE)?;
        if let Some(guard) = mod_table.get(hash)? {
            let record: ModuleRecord = serde_json::from_slice(guard.value()).unwrap();
            Ok(Some(record))
        } else {
            Ok(None)
        }
    }

    pub fn list_all_modules(&self) -> Result<Vec<ModuleRecord>, redb::Error> {
        let read_txn = self.db.begin_read()?;
        let mod_table = read_txn.open_table(MODULES_TABLE)?;
        let mut results = Vec::new();
        for item in mod_table.iter()? {
            let (_k, v) = item?;
            let record: ModuleRecord = serde_json::from_slice(v.value()).unwrap();
            results.push(record);
        }
        Ok(results)
    }

    pub fn update_counter(&self, query_key: &str, success: bool) -> Result<(), redb::Error> {
        let write_txn = self.db.begin_write()?;
        {
            let mut table = write_txn.open_table(ROUTING_COUNTERS)?;
            let current = match table.get(query_key)? {
                Some(v) => v.value(),
                None => 0,
            };
            let updated = if success {
                current.saturating_add(1)
            } else {
                current.saturating_sub(1)
            };
            table.insert(query_key, updated)?;
        }
        write_txn.commit()?;
        Ok(())
    }
}
