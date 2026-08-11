"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DISCIPLINES } from "@/lib/disciplines";
import { uploadBook } from "@/lib/api";
import { toast } from "sonner";

export function UploadDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [discipline, setDiscipline] = useState(DISCIPLINES[0].key);
  const [uploading, setUploading] = useState(false);
  const [progressPct, setProgressPct] = useState(0);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const jobId = await uploadBook(file, discipline, (p) => {
        setProgressPct(Math.round((100 * p.bytesUploaded) / p.totalBytes));
      });
      setOpen(false);
      router.push(`/jobs/${jobId}`);
    } catch (err) {
      toast.error("Upload failed", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setUploading(false);
      setProgressPct(0);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !uploading && setOpen(next)}>
      <DialogTrigger render={<Button size="lg" />}>Add textbook</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a textbook</DialogTitle>
          <DialogDescription>
            Ingested once, shared with the whole department. A 2000-page
            scan can take a while — you can close this and come back, the
            upload and ingest both resume from where they left off.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="pdf-file">PDF file</Label>
            <input
              id="pdf-file"
              type="file"
              accept="application/pdf"
              disabled={uploading}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm"
            />
          </div>
          <div className="grid gap-2">
            <Label>Discipline</Label>
            <Select
              value={discipline}
              onValueChange={(v) => v && setDiscipline(v)}
              disabled={uploading}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DISCIPLINES.map((d) => (
                  <SelectItem key={d.key} value={d.key}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {uploading && (
            <div className="grid gap-1.5">
              <Progress value={progressPct} />
              <p className="text-xs text-muted-foreground">
                Uploading… {progressPct}%
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading ? "Uploading…" : "Upload and ingest"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
