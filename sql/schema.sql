-- Run this if you need to add new columns to existing DB
-- (If starting fresh, FastAPI creates tables automatically)

ALTER TABLE invoices ADD COLUMN IF NOT EXISTS gstin VARCHAR(50);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS hsn_sac VARCHAR(50);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS vendor_code VARCHAR(50);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS cgst FLOAT DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS sgst FLOAT DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS igst FLOAT DEFAULT 0;

ALTER TABLE invoice_lines ADD COLUMN IF NOT EXISTS rate FLOAT DEFAULT 0;
