"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export function AppHeader() {
  const { token, setToken } = useAuth();
  const [draft, setDraft] = useState(token ?? "");

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Practice Forge
        </Link>
        <Popover>
          <PopoverTrigger render={<Button variant="outline" size="sm" />}>
            {token ? "Faculty token set" : "Set faculty token"}
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80">
            <div className="grid gap-3">
              <div className="space-y-1">
                <p className="text-sm font-medium">Faculty token</p>
                <p className="text-xs text-muted-foreground">
                  Needed to generate, reshuffle, or issue a new set — your
                  administrator hands this to you once.
                </p>
              </div>
              <Label htmlFor="faculty-token" className="sr-only">
                Faculty token
              </Label>
              <Input
                id="faculty-token"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="paste your token"
                type="password"
              />
              <div className="flex justify-end gap-2">
                {token && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setToken(null);
                      setDraft("");
                    }}
                  >
                    Clear
                  </Button>
                )}
                <Button size="sm" onClick={() => setToken(draft || null)}>
                  Save
                </Button>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </header>
  );
}
