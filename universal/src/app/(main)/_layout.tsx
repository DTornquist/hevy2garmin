import { Tabs } from "expo-router";
import { type ColorValue } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { tabBarScreenOptions } from "soma-style";

/* Bottom tab bar, matching the soma design system. hevy2garmin has five
   sections (Sync / Workouts / History / Mappings / Settings). The bar's look
   comes from soma-style's shared tabBarScreenOptions so it stays identical to
   soma + macro-engine; routing stays app-local. */
type IconName = React.ComponentProps<typeof Ionicons>["name"];
const tabIcon =
  (name: IconName) =>
  ({ color, size }: { color: ColorValue; size: number }) => (
    <Ionicons name={name} size={size} color={color as string} />
  );

export default function MainLayout() {
  return (
    <SafeAreaView edges={["top"]} className="flex-1 bg-base">
      <Tabs screenOptions={tabBarScreenOptions}>
        <Tabs.Screen name="sync" options={{ title: "Sync", tabBarIcon: tabIcon("sync-outline") }} />
        <Tabs.Screen name="workouts" options={{ title: "Workouts", tabBarIcon: tabIcon("barbell-outline") }} />
        <Tabs.Screen name="history" options={{ title: "History", tabBarIcon: tabIcon("time-outline") }} />
        <Tabs.Screen name="mappings" options={{ title: "Mappings", tabBarIcon: tabIcon("git-compare-outline") }} />
        <Tabs.Screen name="settings" options={{ title: "Settings", tabBarIcon: tabIcon("settings-outline") }} />
      </Tabs>
    </SafeAreaView>
  );
}
