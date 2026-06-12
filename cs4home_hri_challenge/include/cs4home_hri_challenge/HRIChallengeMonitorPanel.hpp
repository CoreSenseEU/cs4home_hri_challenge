#ifndef CS4HOME_HRI_CHALLENGE__HRI_CHALLENGE_MONITOR_PANEL_HPP_
#define CS4HOME_HRI_CHALLENGE__HRI_CHALLENGE_MONITOR_PANEL_HPP_

#include "cs4home_hri_challenge/msg/module_transition_event.hpp"

#include "rclcpp/rclcpp.hpp"
#include "rviz_common/panel.hpp"

#include <QLabel>
#include <QTableWidget>

namespace cs4home_hri_challenge
{

class HRIChallengeMonitorPanel : public rviz_common::Panel
{
  Q_OBJECT

public:
  explicit HRIChallengeMonitorPanel(QWidget * parent = nullptr);

  void onInitialize() override;

private:
  using ModuleTransitionEvent = cs4home_hri_challenge::msg::ModuleTransitionEvent;

  void handleEvent(const ModuleTransitionEvent::SharedPtr msg);
  void updateEventView(const ModuleTransitionEvent & msg);
  void resetDisplay();
  void saveTableToFile();
  QString escapeCsv(const QString & value) const;
  QString formatTimestamp(const builtin_interfaces::msg::Time & stamp) const;
  QString statusText(const ModuleTransitionEvent & msg) const;
  QString transitionStyle(const ModuleTransitionEvent & msg) const;
  QString statusStyle(const ModuleTransitionEvent & msg) const;
  void applyRowStyle(int row, const ModuleTransitionEvent & msg);

  QLabel * current_flow_label_ = nullptr;
  QLabel * current_module_label_ = nullptr;
  QLabel * current_transition_label_ = nullptr;
  QLabel * current_status_label_ = nullptr;
  QLabel * current_elapsed_label_ = nullptr;
  QLabel * recovery_label_ = nullptr;
  QTableWidget * event_table_ = nullptr;

  rclcpp::Node::SharedPtr node_;
  rclcpp::Subscription<ModuleTransitionEvent>::SharedPtr event_subscriber_;
};

}  // namespace cs4home_hri_challenge

#endif  // CS4HOME_HRI_CHALLENGE__HRI_CHALLENGE_MONITOR_PANEL_HPP_
