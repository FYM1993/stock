"""
测试Qlib Order的正确用法

验证Order.amount参数的含义
"""

from qlib.backtest import Order
import pandas as pd

# 测试1: 检查Order的参数
print("="*60)
print("测试Qlib Order参数")
print("="*60)

try:
    order = Order(
        stock_id="000001.SZ",
        amount=0.3,  # 这个到底是什么？比例？股数？金额？
        direction=Order.BUY,
        factor=1.0,
        start_time=pd.Timestamp("2025-01-01"),
        end_time=pd.Timestamp("2025-01-02")
    )
    
    print("\n✅ Order创建成功")
    print(f"stock_id: {order.stock_id}")
    print(f"amount: {order.amount}")
    print(f"direction: {order.direction}")
    print(f"factor: {order.factor}")
    print(f"start_time: {order.start_time}")
    print(f"end_time: {order.end_time}")
    
    # 检查Order类的文档字符串
    print("\n" + "="*60)
    print("Order.__init__的文档:")
    print("="*60)
    if Order.__init__.__doc__:
        print(Order.__init__.__doc__)
    else:
        print("无文档")
    
    # 检查Order.amount的注释
    print("\n" + "="*60)
    print("Order类的所有属性:")
    print("="*60)
    for attr in dir(order):
        if not attr.startswith('_'):
            print(f"  {attr}: {getattr(order, attr, 'N/A')}")
    
except Exception as e:
    print(f"❌ Order创建失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("结论：需要查看Qlib源码确定amount的含义")
print("="*60)
