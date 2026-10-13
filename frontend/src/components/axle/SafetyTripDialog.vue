<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { AlertTriangleIcon } from "@lucide/vue";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAxleStore } from "@/stores/useAxleStore";

const axleStore = useAxleStore();
const isOpen = ref(false);
const displayedTripId = ref<number | null>(null);
const trip = computed(() => axleStore.telemetry.safety.last_trip);
const isFeedbackTimeout = computed(
  () => trip.value?.metric === "feedback_timeout",
);
const description = computed(() =>
  isFeedbackTimeout.value
    ? "使能期间未按时收到 MCU 反馈，上位机已失去闭环监控并执行急停互锁。请检查 MCU 供电与 CAN 线束后再恢复操作。"
    : "监测到反馈参数越限，上位机已执行急停互锁。请确认现场安全后再恢复操作。",
);
const reasonTitle = computed(() =>
  isFeedbackTimeout.value ? "反馈中断" : "越限原因",
);

watch(
  () => trip.value?.trip_id,
  (tripId) => {
    if (tripId !== undefined && tripId !== displayedTripId.value) {
      displayedTripId.value = tripId;
      isOpen.value = true;
    }
  },
  { immediate: true },
);

function acknowledge() {
  isOpen.value = false;
}
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent :show-close-button="false">
      <DialogHeader>
        <DialogTitle>自动安全停机已触发</DialogTitle>
        <DialogDescription>
          {{ description }}
        </DialogDescription>
      </DialogHeader>

      <Alert v-if="trip" variant="destructive">
        <AlertTriangleIcon />
        <AlertTitle>{{ reasonTitle }}</AlertTitle>
        <AlertDescription>
          {{ trip.message }}
        </AlertDescription>
      </Alert>

      <DialogFooter>
        <Button type="button" @click="acknowledge"> 我已知悉 </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
