import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";

import type { PathTestRecord } from "./use-path-workbench";

export function PathTestHistory({
  open,
  onOpenChange,
  records,
  onRestore,
  onClear,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  records: PathTestRecord[];
  onRestore: (record: PathTestRecord) => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{t("routing.testHistory")}</SheetTitle>
          <SheetDescription>
            {t("routing.last50TestsInThisPageSessionRestoringA")}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-auto px-4">
          {records.length ? (
            records.map((item) => (
              <div key={item.id} className="space-y-2 border-b py-4">
                <p className="break-words text-sm font-medium">
                  {item.label} · {item.configuration}
                </p>
                <p className="text-xs text-muted-foreground">
                  {new Date(item.createdAt).toLocaleTimeString()} ·{" "}
                  {item.error
                    ? t("routing.failed")
                    : `HTTP ${item.result?.status}`}
                </p>
                <p className="break-all font-mono text-xs">
                  {item.input.request.split("\n")[0]}
                </p>
                <Button
                  variant="outline"
                  className="min-h-11"
                  onClick={() => {
                    onRestore(item);
                    onOpenChange(false);
                  }}
                >
                  {t("routing.restoreRequestAndResult")}
                </Button>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("routing.noTestHistoryYet")}
            </p>
          )}
        </div>
        <div className="border-t p-4">
          <Button
            variant="ghost"
            className="min-h-11"
            disabled={!records.length}
            onClick={onClear}
          >
            {t("routing.clearHistory")}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
