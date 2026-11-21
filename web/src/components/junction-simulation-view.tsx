"use client";

import { SirenIcon } from "@phosphor-icons/react";
import { motion } from "motion/react";
import dynamic from "next/dynamic";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DIRECTION_LABEL,
  emergencyDirections,
  VEHICLE_COLOR,
  VEHICLE_LABEL,
  VEHICLE_SHAPE,
  VEHICLE_TYPES,
} from "@/lib/junction-scene";
import type { NetworkGeometry, TrafficState } from "@/lib/types";

function emergencySummary(trafficState: TrafficState): string {
  const directions = emergencyDirections(trafficState);
  if (directions.length === 0) return "";
  const labels = directions.map((direction) => DIRECTION_LABEL[direction]);
  return `, emergency vehicle present on ${labels.join(", ")}`;
}

const JunctionPixiCanvas = dynamic(
  () => import("./junction-pixi-canvas").then((mod) => mod.JunctionPixiCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="aspect-square w-full max-w-3xl animate-pulse rounded-lg border border-border bg-muted/30" />
    ),
  },
);

export function JunctionSimulationView({
  geometry,
  trafficState,
}: {
  geometry: NetworkGeometry | null;
  trafficState: TrafficState | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-base font-semibold">
          Live Junction
          {trafficState && (
            <motion.span
              aria-hidden
              className="inline-block size-1.5 rounded-full bg-emerald-500"
              animate={{ opacity: [1, 0.35, 1] }}
              transition={{
                duration: 1.6,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }}
            />
          )}
        </CardTitle>
        <CardDescription>
          The Sapon Under-bridge Junction, rendered from live SUMO vehicle
          positions
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!geometry ? (
          <p className="text-xs text-muted-foreground">
            Loading junction geometry…
          </p>
        ) : (
          <>
            {trafficState && emergencyDirections(trafficState).length > 0 && (
              <Alert
                variant="destructive"
                className="animate-pulse border-destructive/60 bg-destructive/15"
              >
                <SirenIcon />
                <AlertTitle>Emergency vehicle detected</AlertTitle>
                <AlertDescription>
                  Priority approach:{" "}
                  {emergencyDirections(trafficState)
                    .map((direction) => DIRECTION_LABEL[direction])
                    .join(", ")}
                </AlertDescription>
              </Alert>
            )}
            <div role="img" aria-label="Live junction simulation">
              <JunctionPixiCanvas
                geometry={geometry}
                trafficState={trafficState}
              />
              <span className="sr-only">
                {trafficState
                  ? `${trafficState.vehicles.length} vehicles on the junction, active phase ${trafficState.activePhase}${emergencySummary(trafficState)}`
                  : "Junction idle, no live traffic state"}
                . Map orientation: north is up, east is right, south is down,
                and west is left.
              </span>
            </div>
            <VehicleLegend />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function VehicleLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      {VEHICLE_TYPES.map((type) => (
        <div key={type} className="flex items-center gap-1.5">
          <svg viewBox="-10 -12 20 24" className="h-6 w-5" aria-hidden="true">
            <polygon
              points={VEHICLE_SHAPE[type](
                type === "motorcycle"
                  ? 6
                  : type === "car" || type === "emergency"
                    ? 8
                    : 7,
              )
                .map((p) => p.join(","))
                .join(" ")}
              fill={VEHICLE_COLOR[type]}
              stroke="#252525"
              strokeWidth="0.7"
            />
            {type === "car" && (
              <rect x="-2.2" y="-3" width="4.4" height="3.2" fill="#fff7ca" />
            )}
            {type === "bus" && (
              <>
                <rect x="-2" y="-5.2" width="4" height="2" fill="#f5fbff" />
                <rect x="-2" y="-1" width="4" height="2" fill="#f5fbff" />
              </>
            )}
            {type === "truck" && (
              <rect x="-2.5" y="-5.2" width="5" height="2.5" fill="#ffedcc" />
            )}
            {type === "emergency" && (
              <path
                d="M-2.6 0h5.2M0 -2.6v5.2"
                stroke="white"
                strokeWidth="1.5"
              />
            )}
          </svg>
          {VEHICLE_LABEL[type]}
        </div>
      ))}
    </div>
  );
}
