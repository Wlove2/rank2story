# Evidence packet selection

Pass a frozen `normalized/evidence_packet.json` produced by a successful market scan. Verify the associated `run_manifest.json`, `acquisition_manifest.json`, source coverage report, and recorded SHA-256 before candidate generation.

Do not splice older atoms or a packet from one scan with another scan's manifest. A failed integrity or coverage gate is a stop, not an invitation to use stale data.

For public examples, generate synthetic book lists and synthetic timestamps; never redistribute actual ranking dumps or copyrighted article text.